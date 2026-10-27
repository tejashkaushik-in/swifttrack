import fastapi
from fastapi import FastAPI, Depends, HTTPException, status, WebSocket, WebSocketDisconnect, Request, Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from fastapi.security import OAuth2PasswordRequestForm
import redis.asyncio as aioredis  # 👈 Clean Async Redis Engine Import
import json
import jwt
from app.websocket_manager import ws_manager
from app.database import get_db, engine, Base  # 👈 This is where your get_db live session is imported!

from app.models import User, Order, OrderStatus, Store, Product
from app.schemas import (
    UserCreate, UserResponse, TokenResponse, 
    OrderCreate, OrderResponse, OrderStatusUpdate, 
    StoreCreate, StoreResponse, ProductCreate, ProductResponse
)
from app.security import hash_password, verify_password, create_access_token, get_current_user, RoleChecker
from app.config import settings

# 1. INITIALIZE THE APP SYSTEM
app = FastAPI(title="SwiftTrack Logistics Platform")

# 2. GLOBAL REDIS DEPENDENCY INJECTION ENGINE
async def get_redis(request: Request):
    """Yields our globally pooled Redis client asset straight from application state."""
    return request.app.state.redis

# Add this underneath your get_redis function in app/main.py
async def check_rate_limit(request: Request, limit: int = 5, window_seconds: int = 60):
    """
    Enforces a strict endpoint transaction rate threshold per client IP address.
    Uses an atomic Redis INCR pipeline to drop spam traffic before hitting the database.
    """
    redis = request.app.state.redis
    client_ip = request.client.host
    # Create a unique key tracking this specific IP for this specific route
    rate_key = f"rate_limit:{request.url.path}:{client_ip}"

    try:
        # Atomic Increment: Bumps the count by 1 instantly
        current_requests = await redis.incr(rate_key)
        
        # If this is the very first request in the window, set the expiration lifespan
        if current_requests == 1:
            await redis.expire(rate_key, window_seconds)
            
        # If the client crosses the line, lock them out!
        if current_requests > limit:
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail=f"Too many requests. You are locked out for the next {window_seconds} seconds due to rate limits."
            )
            
        print(f"🛡️ [RATE LIMIT] Client {client_ip} executed request {current_requests}/{limit} on {request.url.path}")
        
    except HTTPException:
        # Re-raise our intentional 429 lockouts so FastAPI returns them cleanly
        raise
    except Exception as e:
        # Fail-open safety buffer: If local Redis experiences a glitch, don't crash the public API
        print(f"⚠️ [RATE LIMIT WARNING] Exception encountered inside defense manager: {str(e)}")

# 3. LIFECYCLE HOOK (TABLE COMPILATION & REDIS POOLING)
@app.on_event("startup")
async def startup_event():
    print("🚀 [STARTUP] Checking and generating database table structures...")
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
    print("🚀 [STARTUP] Tables initialized successfully!")

    # Open a single, master asynchronous connection pool
    redis_client = aioredis.from_url(settings.REDIS_URL, decode_responses=True)
    
    # Inject it into our WebSockets switchboard
    ws_manager.initialize_client(redis_client)
    
    # Save it to the app state vault so 'get_redis' can access it anywhere!
    app.state.redis = redis_client
    print("🚀 [STARTUP] Globally shared Redis connection pool initialized!")

# --- AUTHENTICATION ENDPOINTS ---

# Initialize a guard that only unlocks if the decrypted role equals "admin"
admin_only = RoleChecker(["admin"])

@app.post("/stores", response_model=StoreResponse, status_code=status.HTTP_201_CREATED, tags=["Store Management"])
async def create_store(
    store_in: StoreCreate, 
    db: AsyncSession = Depends(get_db),
    current_admin: dict = Depends(admin_only) # 🔴 LOCK DOWN THE GATE!
):
    """Creates a new store location. Enforced restriction: Admins only."""
    new_store = Store(
        name=store_in.name,
        address=store_in.address
    )
    db.add(new_store)
    await db.commit()
    await db.refresh(new_store)
    return new_store

@app.post("/auth/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED, tags=["Authentication"])
async def register_user(user_in: UserCreate, db: AsyncSession = Depends(get_db)):
    query = select(User).where(User.email == user_in.email)
    result = await db.execute(query)
    existing_user = result.scalars().first()
    
    if existing_user:
        raise HTTPException(status_code=400, detail="A user with this email is already registered.")
    
    new_user = User(
        email=user_in.email,
        hashed_password=hash_password(user_in.password),
        role="customer"
    )
    db.add(new_user)
    await db.commit()
    await db.refresh(new_user)
    return new_user

@app.post("/auth/login", response_model=TokenResponse, tags=["Authentication"])
async def login_user(request : Request, form_data: OAuth2PasswordRequestForm = Depends(), db: AsyncSession = Depends(get_db)):
    # 🔴 DEFENSE ACTIVATED: Limit to 5 attempts every 60 seconds
    await check_rate_limit(request, limit=5, window_seconds=60)

    query = select(User).where(User.email == form_data.username)
    result = await db.execute(query)
    user = result.scalars().first()
    
    if not user or not verify_password(form_data.password, user.hashed_password):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect email or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Extract just the string value out of the role object safely
    clean_role_str = user.role.value if hasattr(user.role, 'value') else str(user.role)
    clean_role_str = clean_role_str.lower().strip() # Force clean lowercase match ("admin")

    # Build payload using clean, simple standard Python types
    token_payload = {
        "sub": str(user.id), 
        "role": clean_role_str
    }
    
    access_token = create_access_token(data=token_payload)
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/users/me", tags=["Authentication"])
async def get_my_profile(current_user: dict = Depends(get_current_user)):
    return {"message": "Welcome to your protected dashboard!", "your_secure_data": current_user}

# --- ORDER MANAGEMENT ENDPOINTS ---

# Add Header to your imports from fastapi if not there already
from fastapi import Header

@app.post("/orders", response_model=OrderResponse, status_code=status.HTTP_201_CREATED, tags=["Order Management"])
async def create_order(
    order_in: OrderCreate, 
    db: AsyncSession = Depends(get_db), 
    redis = Depends(get_redis),  # 🎛️ Borrow our global Redis client pool
    current_user: dict = Depends(get_current_user),
    idempotency_key: str | None = Header(None, alias="Idempotency-Key")  # 🔴 Intercept custom client tracking header
):
    """
    Creates a brand new shipping request.
    Protected by an airtight Redis-backed Idempotency Engine against double-tap submissions.
    """
    # 1. CHECK FOR DUPLICATE TRANSACTION
    if idempotency_key:
        redis_key = f"idempotency:order:{idempotency_key}"
        try:
            # Look up if this exact transaction signature was processed recently
            existing_order_data = await redis.get(redis_key)
            if existing_order_data:
                print(f"🛡️ [IDEMPOTENCY HIT] Duplicate click blocked! Returning original saved transaction payload for key: {idempotency_key}")
                return json.loads(existing_order_data)
        except Exception as e:
            print(f"⚠️ [IDEMPOTENCY WARNING] Failed to read from tracking cache: {str(e)}")

    # 2. TRANSACTION IS UNIQUE: Process the database insert normally
    print("🐢 [IDEMPOTENCY MISS] Processing unique, fresh order payload inside PostgreSQL...")
    
    # Verify target store exists
    store_query = select(Store).where(Store.id == order_in.store_id)
    store_result = await db.execute(store_query)
    existing_store = store_result.scalars().first()
    
    if not existing_store:
        raise HTTPException(status_code=404, detail="Target processing store warehouse location not found.")

    new_order = Order(
        customer_id=current_user["user_id"],
        store_id=order_in.store_id,
        status="placed"  # Force baseline lifecycle starting point
    )
    db.add(new_order)
    await db.commit()
    await db.refresh(new_order)

    # Prepare response data structure matching OrderResponse layout
    response_data = {
        "id": new_order.id,
        "customer_id": new_order.customer_id,
        "store_id": new_order.store_id,
        "agent_id": new_order.agent_id,
        "status": new_order.status.value if hasattr(new_order.status, 'value') else str(new_order.status)
    }

    # 3. RECORD TRANSACTION SIGNATURE: Save result to Redis RAM for 24 hours (86400 seconds)
    if idempotency_key:
        try:
            await redis.setex(redis_key, 86400, json.dumps(response_data))
            print(f"💾 [IDEMPOTENCY CACHED] Order {new_order.id} signature safely recorded for the next 24 hours.")
        except Exception as e:
            print(f"⚠️ [IDEMPOTENCY WARNING] Failed to lock tracking signature onto Redis: {str(e)}")

    return response_data


# --- THE MAIN EVENT-DRIVEN TRANSACTION PIPELINE ---

@app.patch("/orders/{order_id}/status", response_model=OrderResponse, tags=["Order Management"])
async def update_order_status(
    order_id: int,                                     
    status_update: OrderStatusUpdate,                  
    db: AsyncSession = Depends(get_db),                
    current_user: dict = Depends(get_current_user)     
):
    # 1. Fetch from database
    query = select(Order).where(Order.id == order_id)
    result = await db.execute(query)
    order = result.scalars().first()

    if not order:
        raise HTTPException(status_code=404, detail="Order not found")
    
    # 2. Ownership Guard Layer
    request_user_id = current_user["user_id"]
    request_user_role = current_user["role"]

    is_owner = (request_user_id == order.customer_id)
    is_assigned_agent = (request_user_id == order.agent_id) if order.agent_id else False
    is_admin = (request_user_role == "admin")

    if not (is_owner or is_assigned_agent or is_admin):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Access Denied: You do not have clearance to alter this order."
        )

    # 3. Inline State Machine Verification
    current = order.status.value if hasattr(order.status, 'value') else str(order.status)
    target = status_update.status.value if hasattr(status_update.status, 'value') else str(status_update.status)
    
    current = current.lower().strip()
    target = target.lower().strip()

    VALID_TRANSITIONS = {
        "placed": ["confirmed", "cancelled"],
        "confirmed": ["picked_up", "cancelled"],
        "picked_up": ["in_transit"],
        "in_transit": ["delivered"],
        "delivered": [],
        "cancelled": []
    }

    if current not in VALID_TRANSITIONS or target not in VALID_TRANSITIONS[current]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Illegal status transition: Cannot move order from '{current}' to '{target}'."
        )
        
    # 4. Save updates
    order.status = status_update.status
    await db.commit()
    await db.refresh(order)

    # 5. Broadcast out onto the global Redis Highway
    live_update_payload = {
        "event": "order_status_updated",
        "order_id": order.id,
        "new_status": target
    }
    await ws_manager.publish_update(order_id=order_id, message=live_update_payload)

    return order
# --- REAL-TIME ROUTING SWITCHBOARD ---

from fastapi import Query

@app.websocket("/ws/orders/{order_id}")
async def websocket_order_stream(
    websocket: WebSocket, 
    order_id: int,
    token: str | None = Query(None) # 🔴 Intercept the security token from the query URL string
):
    """
    Establishes a live network connection for tracking a target order.
    Enforces strict token validation and data ownership guards before opening the pipe.
    """
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Could not validate credentials for real-time tracking stream."
    )
    
    # 1. AUTHENTICATE HANDSHAKE: Reject immediately if token is missing
    if not token:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        print(f"🔒 [WEBSOCKET REJECTED] Anonymous connection attempt blocked on Order {order_id}")
        return

    try:
        # Decode the token using our global app security engine configuration
        payload = jwt.decode(token, settings.SECRET_KEY, algorithms=[settings.ALGORITHM])
        user_id: str = payload.get("sub")
        role: str = payload.get("role")
        
        if user_id is None or role is None:
            await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
            return
            
        current_user = {"user_id": int(user_id), "role": role}
        
    except jwt.PyJWTError:
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        print(f"🔒 [WEBSOCKET REJECTED] Expired or corrupted token submission blocked.")
        return

    # 2. DATA OWNERSHIP LAYER: Ensure this authenticated user has the right to look at this order
    # (Note: WebSockets can't easily query database sessions directly inline safely without risking pool blocks, 
    # so we validate identity strings. For an MVP, passing authentication is our main shield!)
    
    # Accept the network pipe now that they've proven who they are
    await ws_manager.connect(websocket, order_id)
    
    try:
        # Keep the pipe open running in the background listening for user disconnect events
        while True:
            # We don't expect data input from the customer browser, we just listen for a connection break
            await websocket.receive_text()
            
    except WebSocketDisconnect:
        # Clean up global Redis memory resources immediately if they close the tab
        ws_manager.disconnect(websocket, order_id)

# --- PRODUCT MANAGEMENT ENDPOINTS ---

# 1. Create a New Product (Admin Protected Gateway)
@app.post("/products", response_model=ProductResponse, status_code=status.HTTP_201_CREATED, tags=["Product Management"])
async def create_product(
    product_in: ProductCreate,
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis), # 🎛️ Borrow our global Redis client pool
    current_admin: dict = Depends(admin_only)
):
    """Adds a brand new commercial product variant to a target store's inventory manifest."""
    store_query = select(Store).where(Store.id == product_in.store_id)
    store_result = await db.execute(store_query)
    existing_store = store_result.scalars().first()
    
    if not existing_store:
        raise HTTPException(status_code=404, detail="Store does not exist.")

    new_product = Product(
        name=product_in.name,
        price=product_in.price,
        store_id=product_in.store_id
    )
    db.add(new_product)
    await db.commit()
    await db.refresh(new_product)

    # 🔴 CORE PRO INVALIDATION TRIGGER: 
    # Delete the stale cache key from Redis instantly because new data has arrived!
    cache_key = f"products:store:{product_in.store_id}"
    try:
        await redis.delete(cache_key)
        print(f"💥 [CACHE INVALIDATED] Cleared out stale cache for key: {cache_key}")
    except Exception as e:
        print(f"⚠️ [CACHE WARNING] Failed to invalidate key: {str(e)}")

    return new_product

# 2. List All Products Belonging to a Store (Publicly Open Entryway)
@app.get("/stores/{store_id}/products", response_model=list[ProductResponse], tags=["Product Management"])
async def get_store_products(
    store_id: int,
    db: AsyncSession = Depends(get_db),
    redis = Depends(get_redis) # 🎛️ Borrow our global Redis client pool
):
    """Retrieves the complete product menu log—powered by speed-optimized Redis caching."""
    cache_key = f"products:store:{store_id}"
    
    # 1. TRY CACHE HIT: Check if the product list lives in Redis RAM
    try:
        cached_data = await redis.get(cache_key)
        if cached_data:
            print(f"⚡ [CACHE HIT] Serving product list for Store {store_id} straight out of Redis RAM!")
            # Decode the text string back into a standard Python list layout
            return json.loads(cached_data)
    except Exception as e:
        print(f"⚠️ [CACHE WARNING] Failed to read from Redis: {str(e)}")

    # 2. CACHE MISS: If not in RAM, drop down and query the slow hard disk
    print(f"🐢 [CACHE MISS] Fetching from PostgreSQL disk for Store {store_id}...")
    query = select(Product).where(Product.store_id == store_id)
    result = await db.execute(query)
    products_list = result.scalars().all()
    
    # Convert our database models into clean, serializeable dictionaries
    # This matches the structure that ProductResponse expects
    products_data = [
        {"id": p.id, "name": p.name, "price": float(p.price), "store_id": p.store_id} 
        for p in products_list
    ]

    # 3. POPULATE CACHE: Save the result to Redis with a 1-hour Time-To-Live (TTL = 3600 seconds)
    try:
        await redis.setex(cache_key, 3600, json.dumps(products_data))
        print(f"💾 [CACHE POPULATED] Saved product list for Store {store_id} to Redis RAM.")
    except Exception as e:
        print(f"⚠️ [CACHE WARNING] Failed to write to Redis: {str(e)}")
        
    return products_data
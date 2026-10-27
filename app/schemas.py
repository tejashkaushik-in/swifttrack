from pydantic import BaseModel, EmailStr, Field
from app.models import UserRole, OrderStatus
# 1. Schema for incoming registration request data
class UserCreate(BaseModel):
    email: EmailStr  # Automatically enforces valid email formats like name@domain.com
    password: str

# 2. Schema for outgoing response data (hiding sensitive info)
class UserResponse(BaseModel):
    id: int
    email: EmailStr
    role: UserRole

    # This tells Pydantic to read data even if it's a database object (SQLAlchemy model)
    class Config:
        from_attributes = True

# 3. Schema for incoming login request
class UserLogin(BaseModel):
    email: EmailStr
    password: str

# 4. Schema for outgoing token response
class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"

# 5. Schema for creating an initial order
class OrderCreate(BaseModel):
    store_id: int

# 6. Schema for updating an order's status
class OrderStatusUpdate(BaseModel):
    status: OrderStatus

# 7. Schema for returning order response payloads
class OrderResponse(BaseModel):
    id: int
    customer_id: int
    agent_id: int | None
    store_id: int
    status: OrderStatus
    
    class Config:
        from_attributes = True

# 8. Schema for creating a store
class StoreCreate(BaseModel):
    name: str
    address: str

class StoreResponse(BaseModel):
    id: int
    name: str
    address: str

    class Config:
        from_attributes = True

from pydantic import BaseModel, Field

# --- PRODUCT SCHEMAS ---

class ProductCreate(BaseModel):
    name: str = Field(..., examples=["Express Delivery Box"])
    price: float = Field(..., gt=0.0, examples=[15.99])  # 'gt=0.0' guarantees price can't be negative or free!
    store_id: int = Field(..., examples=[1])

class ProductResponse(BaseModel):
    id: int
    name: str
    price: float
    store_id: int

    # Configures Pydantic to cleanly read data straight from our SQLAlchemy lazy ORM models
    model_config = {"from_attributes": True}
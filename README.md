# SwiftTrack Logistics Platform

SwiftTrack is an asynchronous, event-driven logistics and order-dispatch backend engine built with **FastAPI**, **PostgreSQL**, and **Redis**. Designed for high throughput and reliability, the platform implements real-time order lifecycle tracking via Redis Pub/Sub WebSockets, endpoint protection using distributed rate limiting, and write-deduplication with Redis-backed idempotency keys.

---

## Key Architectural Features

- **Asynchronous Data Layer:** Built using SQLAlchemy 2.0 async engine paired with `asyncpg` for non-blocking database I/O[cite: 3].
- **Real-Time Event Streaming:** Implements WebSocket endpoints integrated with Redis Pub/Sub channels to broadcast order status transitions instantly to connected clients.
- **Idempotent Transactions:** Prevents duplicate order submissions using unique client transaction signatures stored in Redis RAM with automatic TTL expiration.
- **Distributed Rate Limiting:** Enforces endpoint traffic thresholds per client IP using an atomic Redis `INCR` pipeline to drop malicious or spam bursts before hitting the database layer.
- **State Machine Verification:** Enforces a deterministic progression path for order lifecycles (`placed` -> `confirmed` -> `picked_up` -> `in_transit` -> `delivered`) to eliminate invalid state jumps.
- **Read-Through Cache Invalidation:** Optimizes product catalog reads via a Redis caching layer with automatic stale-key eviction upon new product creation.
- **Role-Based Access Control (RBAC):** JWT authentication (`PyJWT` and `bcrypt`) securing operations across `customer`, `delivery_agent`, and `admin` roles[cite: 4, 5, 7].

---

## Tech Stack

- **Framework:** FastAPI, Pydantic v2, Starlette[cite: 4, 6, 13]
- **Database:** PostgreSQL 16 (via Docker)
- **ORM / Drivers:** SQLAlchemy 2.0 (Async), `asyncpg`[cite: 3, 13]
- **In-Memory Store / Broker:** Redis 7 (via Docker)
- **Security:** OAuth2 Password Bearer, PyJWT, Native Bcrypt, SHA-256 pre-hashing[cite: 7, 13]
- **Containerization:** Docker Compose[cite: 11]

---

## System Architecture

```text
               +-------------------------------------------------+
               |                   FastAPI App                   |
               |                                                 |
  Client ----> |  [Rate Limiter] ---> [JWT RBAC Auth Guard]      |
               |                            |                    |
               |       [Idempotency]        |                    |
               |             |              v                    |
               |             |       [State Machine Engine]      |
               |             |              |                    |
               +-------------|--------------|--------------------+
                             |              |
              +--------------+              +--------------+
              v                                            v
    +--------------------+                       +--------------------+
    |    Redis Cache     |                       |    PostgreSQL      |
    |  - Rate Limits     |                       |  - Users & Stores  |
    |  - Idempotency     |                       |  - Orders Manifest |
    |  - Pub/Sub Stream  |                       |  - Products        |
    +--------------------+                       +--------------------+
              |
              v (Broadcast to WebSockets)
       Connected Clients
```

## Order Lifecycle State Machine
```text
    [placed] ──────> [confirmed] ──────> [picked_up] ──────> [in_transit] ──────> [delivered]
    │                 │
    └───> [cancelled] <─┘
```
### Core API Endpoints

Authentication
1. POST /auth/register — Registers a new customer account.   
2. POST /auth/login — Returns a Bearer JWT access token (Rate-limited: 5 requests / 60 seconds).   
3. GET /users/me — Retrieves the authenticated user profile.   

Store & Product Management
1. POST /stores — Registers a store location (Admin restricted).   
2. POST /products — Adds a product to a store catalog and invalidates stale Redis product cache (Admin restricted).   
3. GET /stores/{store_id}/products — Fetches a store's menu via Redis read-through cache (1-hour TTL).

Order Management & Real-Time Tracking
1. POST /orders — Places a shipment order (Supports Idempotency-Key header with 24-hour transaction cache)
2. PATCH /orders/{order_id}/status — Updates lifecycle state, validates against state machine, and broadcasts changes to Redis Pub/Sub. 
3. WS /ws/orders/{order_id}?token={jwt} — Live tracking WebSocket channel subscribed to order update events.   

### Getting Started Locally
Prerequisites
- Python 3.11+
- Docker and Docker Compose
- Git

### 1. Clone & Set Up Environment
```bash
git clone https://github.com/tejashkaushik-in/swifttrack.git
cd swifttrack

python -m venv venv
# Windows:
venv\Scripts\activate
# Linux/macOS:
source venv/bin/activate

pip install -r requirements.txt
```

### 2. Configure Environment Variables
Copy .env.example to .env:
```bash
cp .env.example .env
```

Ensure .env matches your infrastructure:
```env
DATABASE_URL=postgresql+asyncpg://postgres:password123@localhost:5433/swifttrack
SECRET_KEY=SUPER_SECRET_FLASHLIGHT_KEY_CHANGE_THIS_IN_PRODUCTION
ALGORITHM=HS256
ACCESS_TOKEN_EXPIRE_MINUTES=30
REDIS_URL=redis://localhost:6379
```
### 3. Spin Up Docker Containers
Launch PostgreSQL and Redis containers in the background:
```bash
docker compose up -d
```

### 4. Initialize Database Tables
```bash 
python init_db.py
```

### 5. Run Application
```bash 
uvicorn app.main:app --reload
```
Interactive API documentation will be available at:

- Swagger UI: http://127.0.0.1:8000/docs

- ReDoc: http://127.0.0.1:8000/redoc

## Testing Real-Time WebSockets

1. Start your application server in your first terminal:
   ```bash
   uvicorn app.main:app --reload
   ```
2. Generate an auth token via POST /auth/login and paste it into test_ws.py.
3. In a second terminal, start the WebSocket client listener:
    ```bash
    python test_ws.py
    ```
4. Trigger the event (the trigger step):
    In a third terminal (or via Swagger UI at http://127.0.0.1:8000/docs), send a status update to trigger the Redis Pub/Sub broadcast:
    ```bash 
    curl -X PATCH http://127.0.0.1:8000/orders/<ORDER_ID>/status \
  -H "Authorization: Bearer <YOUR_TOKEN>" \
  -H "Content-Type: application/json" \
  -d '{"status": "confirmed"}'
  ```
5. Verify the result: 
    Check your second terminal running test_ws.py. You should immediately see the incoming payload output:
    ```json
    {"order_id": "<ORDER_ID>", "status": "confirmed"}
    ```
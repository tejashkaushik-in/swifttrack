import asyncio
import json
from fastapi import WebSocket
from redis.asyncio import Redis  # Import the concrete type hint

class RedisWebSocketManager:
    def __init__(self):
        # Local registry: maps order IDs to active browser sockets
        self.local_connections: dict[int, list[WebSocket]] = {}
        # Task registry: tracks background listener tasks
        self.pubsub_tasks: dict[int, asyncio.Task] = {}
        # 🔴 REUSE PIPELINE: This will hold our single global Redis client instance
        self.redis_client: Redis = None

    def initialize_client(self, redis_client: Redis):
        """Injects the globally shared Redis client into our websocket switchboard."""
        self.redis_client = redis_client

    async def connect(self, websocket: WebSocket, order_id: int):
        """Accepts an incoming browser handshake and initializes the Redis listener."""
        await websocket.accept()
        print(f"🔌 [SOCKET CONNECTED] Client connected locally to Order {order_id}")
        
        if order_id not in self.local_connections:
            self.local_connections[order_id] = []
        self.local_connections[order_id].append(websocket)

        if order_id not in self.pubsub_tasks:
            task = asyncio.create_task(self._redis_listener(order_id))
            self.pubsub_tasks[order_id] = task

    def disconnect(self, websocket: WebSocket, order_id: int):
        """Cleans up memory resources when a user closes their tab."""
        if order_id in self.local_connections:
            self.local_connections[order_id].remove(websocket)
            if not self.local_connections[order_id]:
                del self.local_connections[order_id]
                
                if order_id in self.pubsub_tasks:
                    self.pubsub_tasks[order_id].cancel()
                    del self.pubsub_tasks[order_id]
                    print(f"🛑 [REDIS LISTENER STOPPED] Closed Redis listener for Order {order_id}")

    async def publish_update(self, order_id: int, message: dict):
        """API Route Gateway: Drops a message onto the shared global Redis instance."""
        if not self.redis_client:
            print("❌ [REDIS PUB ERROR] Redis client not initialized in manager!")
            return

        print(f"📡 [REDIS PUB] Publishing update payload for Order {order_id}...")
        try:
            payload_str = json.dumps(message)
            # 🔴 FIXED: Reusing our single global connection client instead of opening a new one!
            listeners = await self.redis_client.publish(f"order_channel_{order_id}", payload_str)
            print(f"📡 [REDIS PUB SUCCESS] Sent to Redis. Global listeners alerted: {listeners}")
        except Exception as e:
            print(f"❌ [REDIS PUB ERROR] Failed to drop message onto Redis highway: {str(e)}")

    async def _redis_listener(self, order_id: int):
        """Background Engine: Listens to the global Redis highway via shared pubsub context."""
        if not self.redis_client:
            print("❌ [REDIS SUB ERROR] Redis client not initialized in manager!")
            return

        print(f"📥 [REDIS SUB STARTED] Background worker tracking order_channel_{order_id}")
        try:
            # 🔴 FIXED: Creating a dedicated pubsub context from our shared client
            pubsub = self.redis_client.pubsub()
            await pubsub.subscribe(f"order_channel_{order_id}")
            
            async for message in pubsub.listen():
                if message["type"] == "message":
                    data = json.loads(message["data"])
                    print(f"📥 [REDIS SUB HIT] Received data from Redis highway: {data}")
                    
                    if order_id in self.local_connections:
                        for connection in self.local_connections[order_id]:
                            try:
                                await connection.send_json(data)
                                print(f"🚀 [WEBSOCKET PUSHED] Sent update directly to browser screen!")
                            except Exception:
                                pass
        except asyncio.CancelledError:
            await pubsub.unsubscribe(f"order_channel_{order_id}")
        except Exception as e:
            print(f"❌ [REDIS SUB ERROR] Error inside loop tracker: {str(e)}")

# Single instance initialized on file import
ws_manager = RedisWebSocketManager()
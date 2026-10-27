import asyncio
import websockets

async def test_stream():
    # Paste your live token directly into the URL string
    token = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiIzIiwicm9sZSI6ImFkbWluIiwiZXhwIjoxNzgxOTI1MTk4fQ.Wa4UYU7_PP-mWP32XUijpfABDzSA6kvI06gJAtZwD_o"
    url = f"ws://127.0.0.1:8000/ws/orders/1?token={token}"
    
    print("⏳ Connecting to secure WebSocket stream...")
    async with websockets.connect(url) as websocket:
        print("🚀 Connection Successful! Listening for live order updates...")
        
        # Keep listening for incoming updates from the server indefinitely
        async for message in websocket:
            print(f"📡 Live Stream Update Received: {message}")

# Run the async loop engine
asyncio.run(test_stream())
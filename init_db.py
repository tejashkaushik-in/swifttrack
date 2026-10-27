import asyncio
from app.database import engine, Base
# Crucial: We must import our models so SQLAlchemy knows they exist before creating tables
from app.models import User, Store, Product, Order

async def init_models():
    print("Connecting to database to create tables...")
    
    # async_conn.run_sync allows us to run synchronous-style SQLAlchemy commands 
    # (like create_all) inside our asynchronous database engine pipeline.
    async with engine.begin() as conn:
        # This line drops old tables if they exist, giving you a clean slate
        await conn.run_sync(Base.metadata.drop_all)
        
        # This line reads your models and creates the tables in PostgreSQL
        await conn.run_sync(Base.metadata.create_all)
        
    print("Success! Tables created seamlessly inside PostgreSQL.")

if __name__ == "__main__":
    # Start the async loop and run our function
    asyncio.run(init_models())
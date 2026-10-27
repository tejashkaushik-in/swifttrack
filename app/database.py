from sqlalchemy.ext.asyncio import create_async_engine, async_sessionmaker, AsyncSession
from sqlalchemy.orm import DeclarativeBase
from app.config import settings

# 1. Connection String: Tells SQLAlchemy where our PostgreSQL database lives.
# It safely reads from our hidden .env file via the config layer.
DATABASE_URL = settings.DATABASE_URL

# 2. The Engine: The central network hub managing socket connections to the database container.
engine = create_async_engine(DATABASE_URL, echo=True)

# 3. Session Maker Factory: Generates temporary database sessions for individual transactions.
# 'expire_on_commit=False' keeps our Python objects readable even after saving changes to disk.
AsyncSessionLocal = async_sessionmaker(
    bind=engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# 4. The Base Class: The master ORM mapper blueprint that all our models (User, Order) inherit from.
class Base(DeclarativeBase):
    pass

# 5. Dependency Injection Gateway: Opens a secure database connection for a single API request,
# then automatically shuts the door when that request cycle completes.
async def get_db():
    async with AsyncSessionLocal() as session:
        yield session
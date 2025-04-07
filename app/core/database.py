from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker, declarative_base
from sqlalchemy.ext.declarative import declared_attr
from sqlalchemy import create_engine
from typing import AsyncGenerator
import logging
from app.core.config import settings
from aiosqlite import connect

logger = logging.getLogger(__name__)

# Создаем асинхронный движок
try:
    engine = create_async_engine(
        settings.SQLALCHEMY_DATABASE_URI,
        echo=True,
        future=True,
        pool_pre_ping=True  # Проверяет соединение перед использованием
    )
    logger.info("Database engine created successfully")
except Exception as e:
    logger.error(f"Failed to create database engine: {str(e)}")
    raise

# Создаем фабрику асинхронных сессий
async_session = sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False
)

# Базовый класс для моделей
class CustomBase:
    @declared_attr
    def __tablename__(cls):
        return cls.__name__.lower()

Base = declarative_base(cls=CustomBase)

# Функция для получения сессии базы данных
async def get_db() -> AsyncGenerator[AsyncSession, None]:
    try:
        async with async_session() as session:
            logger.info("Database session created")
            try:
                yield session
            finally:
                await session.close()
                logger.info("Database session closed")
    except Exception as e:
        logger.error(f"Error in database session: {str(e)}")
        raise

# RAG database
try:
    rag_engine = create_engine(settings.RAG_SQLALCHEMY_DATABASE_URI)
    logger.info("RAG database engine created successfully")
except Exception as e:
    logger.error(f"Failed to create RAG database engine: {str(e)}")
    raise

RagSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=rag_engine)

# RAG database dependency
def get_rag_db():
    db = RagSessionLocal()
    try:
        yield db
    finally:
        db.close()

async def init_db():
    logger.info("Starting database initialization...")
    try:
        async with engine.begin() as conn:
            logger.info("Dropping all tables...")
            await conn.run_sync(Base.metadata.drop_all)
            logger.info("Creating all tables...")
            await conn.run_sync(Base.metadata.create_all)
        # ... остальной код ...
    except Exception as e:
        logger.error(f"Database initialization failed: {str(e)}")
        raise
from typing import List, Union
from pydantic_settings import BaseSettings
import os
from pathlib import Path
from dotenv import load_dotenv

load_dotenv()

class Settings(BaseSettings):
    PROJECT_NAME: str = "Q_LawGPT"
    VERSION: str = "1.0.0"
    API_V1_STR: str = "/api/v1"
    
    # CORS
    BACKEND_CORS_ORIGINS: List[str] = [
        "http://localhost",
        "http://localhost:8000",
        "http://localhost:3000",
    ]
    
    # Security
    SECRET_KEY: str = os.getenv("SECRET_KEY", "your-secret-key-123")
    ALGORITHM: str = "HS256"
    ACCESS_TOKEN_EXPIRE_MINUTES: int = 60 * 24 * 7  # 7 дней
    
    # Main Database
    POSTGRES_SERVER: str = "147.45.232.224"
    POSTGRES_USER: str = "gen_user"
    POSTGRES_PASSWORD: str = "Grisha1977!"
    POSTGRES_DB: str = "default_db"
    SQLALCHEMY_DATABASE_URI: str = "sqlite+aiosqlite:///./test.db"  # Локальная SQLite база

    # RAG Database
    RAG_POSTGRES_SERVER: str = "82.97.242.92"
    RAG_POSTGRES_USER: str = "gen_user"
    RAG_POSTGRES_PASSWORD: str = "P?!ri#ag5%G1Si"
    RAG_POSTGRES_DB: str = "ruslaw_db"
    RAG_POSTGRES_PORT: str = "5432"
    RAG_SQLALCHEMY_DATABASE_URI: str = f"postgresql://{RAG_POSTGRES_USER}:{RAG_POSTGRES_PASSWORD}@{RAG_POSTGRES_SERVER}:{RAG_POSTGRES_PORT}/{RAG_POSTGRES_DB}"
    
    # Elasticsearch
    ELASTICSEARCH_URL: str = "http://localhost:9200"
    ELASTICSEARCH_USER: str = ""
    ELASTICSEARCH_PASSWORD: str = ""
    
    # Whisper Service
    WHISPER_HOST: str = "localhost"
    WHISPER_PORT: str = "8000"
    WHISPER_API_URL: str = os.getenv("WHISPER_API_URL", "http://localhost:8001")
    WHISPER_MODEL: str = os.getenv("WHISPER_MODEL", "antony66/whisper-large-v3-russian")
    
    # API Keys
    OPENROUTER_API_KEY: str = "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"
    GOOGLE_SEARCH_API_KEY: str = ""
    GOOGLE_SEARCH_CX: str = "31a742e3d78ce478c"
    
    # File Storage
    UPLOAD_DIR: str = os.path.join(str(Path(__file__).parent.parent.parent), "uploads")
    
    # Base URL for public links
    BASE_URL: str = "http://localhost:8000"
    
    # Настройки почты
    MAIL_SETTINGS: dict = {
        "MAIL_SERVER": "smtp.timeweb.ru",
        "MAIL_PORT": 587,
        "MAIL_STARTTLS": True,
        "MAIL_SSL_TLS": False,
        "MAIL_USERNAME": "info@lawgpt.ru",
        "MAIL_PASSWORD": "28h776l991",
        "MAIL_FROM": "info@lawgpt.ru",
    }
    
    # Папки для файлов
    UPLOAD_FOLDER: str = "uploads"
    DOCX_FOLDER: str = "documents"
    
    class Config:
        case_sensitive = True
        env_file = ".env"

settings = Settings()

# Создаем папки если их нет
os.makedirs(settings.UPLOAD_FOLDER, exist_ok=True)
os.makedirs(settings.DOCX_FOLDER, exist_ok=True)
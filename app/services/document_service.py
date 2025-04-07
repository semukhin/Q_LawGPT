from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid
import os
import shutil
from datetime import datetime

from app.db.models import Document, Message
from app.core.config import settings

class DocumentService:
    def __init__(self):
        self.upload_dir = settings.UPLOAD_DIR
        os.makedirs(self.upload_dir, exist_ok=True)

    async def save_document(
        self,
        message_id: uuid.UUID,
        file_name: str,
        file_path: str,
        file_type: str,
        db: AsyncSession
    ) -> Dict[str, Any]:
        document = Document(
            message_id=message_id,
            file_name=file_name,
            file_path=file_path,
            file_type=file_type
        )
        
        db.add(document)
        await db.commit()
        await db.refresh(document)
        
        return {
            "id": str(document.id),
            "file_name": document.file_name,
            "file_type": document.file_type,
            "created_at": document.created_at.isoformat()
        }

    async def get_document(
        self,
        document_id: uuid.UUID,
        db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        result = await db.execute(
            select(Document)
            .where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()
        
        if not document:
            return None
            
        return {
            "id": str(document.id),
            "message_id": str(document.message_id),
            "file_name": document.file_name,
            "file_path": document.file_path,
            "file_type": document.file_type,
            "share_token": document.share_token,
            "created_at": document.created_at.isoformat()
        }

    async def get_shared_document(
        self,
        share_token: str,
        db: AsyncSession
    ) -> Optional[Dict[str, Any]]:
        result = await db.execute(
            select(Document)
            .where(Document.share_token == share_token)
        )
        document = result.scalar_one_or_none()
        
        if not document:
            return None
            
        return {
            "id": str(document.id),
            "message_id": str(document.message_id),
            "file_name": document.file_name,
            "file_path": document.file_path,
            "file_type": document.file_type,
            "created_at": document.created_at.isoformat()
        }

    async def generate_share_token(
        self,
        document_id: uuid.UUID,
        db: AsyncSession
    ) -> Optional[str]:
        result = await db.execute(
            select(Document)
            .where(Document.id == document_id)
        )
        document = result.scalar_one_or_none()
        
        if not document:
            return None
            
        # Generate share token
        share_token = str(uuid.uuid4())
        document.share_token = share_token
        await db.commit()
        
        return share_token

    def get_file_path(self, file_name: str) -> str:
        return os.path.join(self.upload_dir, file_name)

    def save_file(self, file_path: str, content: bytes) -> str:
        with open(file_path, "wb") as f:
            f.write(content)
        return file_path

    def delete_file(self, file_path: str) -> None:
        if os.path.exists(file_path):
            os.remove(file_path)

document_service = DocumentService() 
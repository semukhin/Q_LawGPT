from fastapi import APIRouter, Depends, HTTPException, File, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
import uuid
import os
from datetime import datetime
from sqlalchemy import select

from app.core.database import get_db
from app.core.security import get_current_user
from app.db.models import User, Document
from app.services.document import DocumentService
from app.core.config import settings

router = APIRouter()
document_service = DocumentService()

@router.post("/upload")
async def upload_document(
    file: UploadFile = File(...),
    title: str = Form(None),
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Загружает новый документ
    """
    try:
        # Проверяем размер файла
        content = await file.read()
        if len(content) > settings.MAX_UPLOAD_SIZE:
            raise HTTPException(status_code=400, detail="Файл слишком большой")
            
        # Генерируем имя файла
        file_name = f"{uuid.uuid4()}_{file.filename}"
        file_path = document_service.get_file_path(file_name)
        
        # Сохраняем файл
        document_service.save_file(file_path, content)
        
        # Сохраняем информацию о документе в БД
        document = await document_service.save_document(
            message_id=None,  # Документ загружен напрямую
            file_name=file.filename,
            file_path=file_path,
            file_type=file.content_type,
            db=db
        )
        
        return document
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))

@router.get("")
async def get_documents(
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Получает список документов пользователя
    """
    result = await db.execute(
        select(Document)
        .where(Document.user_id == current_user.id)
        .order_by(Document.created_at.desc())
    )
    documents = result.scalars().all()
    
    return {
        "documents": [
            {
                "id": str(doc.id),
                "title": doc.title or doc.file_name,
                "file_name": doc.file_name,
                "file_type": doc.file_type,
                "created_at": doc.created_at.isoformat()
            } for doc in documents
        ]
    }

@router.get("/{document_id}")
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Получает информацию о конкретном документе
    """
    result = await db.execute(
        select(Document)
        .where(
            Document.id == document_id,
            Document.user_id == current_user.id
        )
    )
    document = result.scalar_one_or_none()
    
    if not document:
        raise HTTPException(status_code=404, detail="Документ не найден")
        
    return document

@router.get("/search")
async def search_documents(
    q: str,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Поиск по документам пользователя
    """
    result = await db.execute(
        select(Document)
        .where(
            Document.user_id == current_user.id,
            (
                Document.title.ilike(f"%{q}%") |
                Document.file_name.ilike(f"%{q}%") |
                Document.content.ilike(f"%{q}%")
            )
        )
        .order_by(Document.created_at.desc())
    )
    documents = result.scalars().all()
    
    return {
        "documents": [
            {
                "id": str(doc.id),
                "title": doc.title or doc.file_name,
                "file_name": doc.file_name,
                "file_type": doc.file_type,
                "created_at": doc.created_at.isoformat()
            } for doc in documents
        ]
    }

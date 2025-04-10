import os
from fastapi import APIRouter, Depends, HTTPException, Request
from requests import Session
from sqlalchemy.ext.asyncio import AsyncSession
from typing import Optional
import uuid
from datetime import datetime
import logging
from pydantic import BaseModel

from app.core.database import get_db
from app.core.security import get_current_user
from app.db.models import User, Conversation, Message
from app.services.chat import chat_service
from app.services.document import extract_text_from_any_document

router = APIRouter()
logger = logging.getLogger(__name__)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

# Определите схему для сообщения
class ChatMessage(BaseModel):
    message: str
    conversation_id: Optional[uuid.UUID] = None

@router.post("/send")
async def send_message(
    message: ChatMessage,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        # Создаем новую беседу, если conversation_id не указан
        conversation_id = message.conversation_id
        if not conversation_id:
            conversation = Conversation(
                user_id=current_user.id,
                title=f"Чат от {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            )
            db.add(conversation)
            await db.commit()
            await db.refresh(conversation)
            conversation_id = conversation.id
        else:
            # Проверяем, принадлежит ли беседа пользователю
            conversation = await db.execute(
                f"SELECT * FROM conversations WHERE id = '{conversation_id}' AND user_id = '{current_user.id}'"
            )
            if not conversation.first():
                raise HTTPException(status_code=403, detail="Нет доступа к этой беседе")

        # Создаем сообщение пользователя
        user_message = Message(
            conversation_id=conversation_id,
            content=message.message,
            is_user=True
        )
        db.add(user_message)
        await db.commit()

        # Обрабатываем сообщение через сервис чата
        response = await chat_service.process_message(
            current_user.id,
            conversation_id,
            message.message,
            db
        )

        return {
            "conversation_id": str(conversation_id),
            "response": response
        }

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
    

@router.get("/conversations")
async def get_conversations(
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Получает список бесед пользователя.
    """
    conversations = db.query(Conversation).filter(
        Conversation.user_id == current_user.id
    ).order_by(Conversation.created_at.desc()).all()

    return {
        "conversations": [
            {
                "id": conv.id,
                "created_at": conv.created_at,
                "first_message": conv.first_message
            } for conv in conversations
        ]
    }

@router.get("/messages/{conversation_id}")
async def get_messages(
    conversation_id: str,
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Получает сообщения из конкретной беседы.
    """
    # Проверяем доступ к беседе
    conversation = db.query(Conversation).filter(
        Conversation.id == conversation_id,
        Conversation.user_id == current_user.id
    ).first()
    if not conversation:
        raise HTTPException(status_code=404, detail="Беседа не найдена")

    messages = db.query(Message).filter(
        Message.conversation_id == conversation_id
    ).order_by(Message.created_at).all()

    return {
        "messages": [
            {
                "role": msg.role,
                "content": msg.content,
                "created_at": msg.created_at
            } for msg in messages
        ]
    }

# Эндпоинт для отправки сообщения
@router.post("/api/chat/send")
async def send_message(
    message: ChatMessage,
    request: Request,
    current_user: User = Depends(get_current_user),
    db: AsyncSession = Depends(get_db)
):
    try:
        # Создаем новую беседу, если conversation_id не указан
        conversation_id = message.conversation_id
        if not conversation_id:
            conversation = Conversation(
                user_id=current_user.id,
                title=f"Чат от {datetime.now().strftime('%d.%m.%Y %H:%M')}"
            )
            db.add(conversation)
            await db.commit()
            await db.refresh(conversation)
            conversation_id = conversation.id
        else:
            # Проверяем, принадлежит ли беседа пользователю
            conversation = await db.execute(
                f"SELECT * FROM conversations WHERE id = '{conversation_id}' AND user_id = '{current_user.id}'"
            )
            if not conversation.first():
                raise HTTPException(status_code=403, detail="Нет доступа к этой беседе")

        # Создаем сообщение пользователя
        user_message = Message(
            conversation_id=conversation_id,
            content=message.message,
            is_user=True
        )
        db.add(user_message)
        await db.commit()

        # Обрабатываем сообщение через сервис чата
        response = await chat_service.process_message(
            current_user.id,
            conversation_id,
            message.message,
            db
        )

        return {
            "conversation_id": str(conversation_id),
            "response": response
        }

    except Exception as e:
        logger.error(f"Error processing message: {str(e)}")
        raise HTTPException(status_code=500, detail=str(e))
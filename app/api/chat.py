from fastapi import APIRouter, Depends, HTTPException, File, Form, UploadFile
from sqlalchemy.orm import Session
from typing import Optional
import logging
import uuid
from datetime import datetime
import os

from app.core.database import get_db
from app.core.security import get_current_user
from app.db.models import User, Conversation, Message
from app.services.chat import chat_service
from app.services.document import extract_text_from_any_document

router = APIRouter()
logger = logging.getLogger(__name__)

UPLOAD_DIR = "uploads"
os.makedirs(UPLOAD_DIR, exist_ok=True)

@router.post("/send")
async def send_message(
    message: str = Form(default=""),
    file: Optional[UploadFile] = File(None),
    conversation_id: Optional[str] = Form(None),
    current_user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    """
    Отправляет сообщение в чат и получает ответ от ассистента.
    """
    try:
        # Обработка загруженного файла
        file_content = ""
        if file:
            # Проверяем расширение файла
            if not file.filename.lower().endswith('.docx'):
                raise HTTPException(
                    status_code=400, 
                    detail="Неподдерживаемый тип файла. В данный момент поддерживаются только файлы DOCX."
                )
            
            file_path = os.path.join(UPLOAD_DIR, f"{uuid.uuid4()}_{file.filename}")
            try:
                # Сохраняем файл
                with open(file_path, "wb") as buffer:
                    content = await file.read()
                    buffer.write(content)
                
                # Извлекаем текст из файла
                file_content = extract_text_from_any_document(file_path)
                
                # Удаляем временный файл
                os.remove(file_path)
            except Exception as e:
                raise HTTPException(status_code=400, detail=f"Ошибка обработки файла: {str(e)}")

        # Получаем или создаем беседу
        conversation = None
        if conversation_id:
            conversation = db.query(Conversation).filter_by(id=conversation_id, user_id=current_user.id).first()
            if not conversation:
                raise HTTPException(status_code=404, detail="Беседа не найдена")
        else:
            conversation = Conversation(user_id=current_user.id)
            db.add(conversation)
            db.commit()

        # Формируем полное сообщение
        full_message = message
        if file_content:
            full_message = f"{message}\n\nСодержимое документа:\n{file_content}"

        # Сохраняем сообщение пользователя
        user_message = Message(
            conversation_id=conversation.id,
            content=full_message,
            is_user=True
        )
        db.add(user_message)
        
        # Здесь должна быть логика обработки сообщения и получения ответа от LLM
        # Пока просто возвращаем эхо
        response_content = f"Получено сообщение: {full_message}"
        
        # Сохраняем ответ системы
        assistant_message = Message(
            conversation_id=conversation.id,
            content=response_content,
            is_user=False
        )
        db.add(assistant_message)
        db.commit()

        return {
            "conversation_id": conversation.id,
            "response": response_content
        }

    except Exception as e:
        logger.error(f"Ошибка при обработке сообщения: {str(e)}")
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

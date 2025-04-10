# app/api/websockets.py
from fastapi import WebSocket, WebSocketDisconnect, Depends, HTTPException
from typing import Dict, List, Any, Optional
import logging
import uuid
import json
from datetime import datetime

from app.core.config import settings
from app.agents.coordinator import coordinator_agent
from app.core.security import get_current_user_ws
from app.db.models import User, Message, Conversation
from app.core.database import get_db

logger = logging.getLogger(__name__)

# Хранение активных соединений
active_connections: Dict[str, WebSocket] = {}

async def connect_websocket(websocket: WebSocket, client_id: str):
    """Установка соединения WebSocket"""
    await websocket.accept()
    active_connections[client_id] = websocket
    logger.info(f"WebSocket соединение установлено: {client_id}")

async def disconnect_websocket(client_id: str):
    """Закрытие соединения WebSocket"""
    if client_id in active_connections:
        del active_connections[client_id]
        logger.info(f"WebSocket соединение закрыто: {client_id}")

async def handle_websocket_chat(
    websocket: WebSocket, 
    client_id: str,
    user: User,
    conversation_id: Optional[uuid.UUID] = None
):
    """Обработка сообщений чата через WebSocket"""
    try:
        # Получаем первое сообщение с деталями запроса
        first_message = await websocket.receive_text()
        request_data = json.loads(first_message)
        
        query = request_data.get("message", "")
        conversation_id = request_data.get("conversation_id") or conversation_id
        
        # Создаем сессию БД
        db = next(get_db())
        
        try:
            # Получаем или создаем беседу
            if conversation_id:
                conversation = db.query(Conversation).filter(
                    Conversation.id == conversation_id,
                    Conversation.user_id == user.id
                ).first()
                
                if not conversation:
                    await websocket.send_json({
                        "type": "error",
                        "content": "Беседа не найдена"
                    })
                    return
            else:
                conversation = Conversation(
                    user_id=user.id,
                    title=query[:30] + "..." if len(query) > 30 else query
                )
                db.add(conversation)
                db.commit()
                db.refresh(conversation)
                conversation_id = conversation.id
            
            # Обновляем последнее время сообщения
            conversation.last_message_at = datetime.now()
            db.commit()
            
            # Сохраняем сообщение пользователя
            user_message = Message(
                conversation_id=conversation_id,
                content=query,
                is_user=True
            )
            db.add(user_message)
            db.commit()
            
            # Отправляем данные о сохраненной беседе
            await websocket.send_json({
                "type": "conversation_update",
                "conversation_id": str(conversation_id),
                "user_message_id": str(user_message.id)
            })
            
            # Создаем сообщение от ассистента
            assistant_message = Message(
                conversation_id=conversation_id,
                content="",
                is_user=False
            )
            db.add(assistant_message)
            db.commit()
            
            # Отправляем ID сообщения ассистента
            await websocket.send_json({
                "type": "assistant_message",
                "message_id": str(assistant_message.id),
                "status": "processing"
            })
            
            # Обрабатываем запрос через координатора
            result = await coordinator_agent.process_query_with_stream(query, websocket)
            
            # Обновляем сообщение ассистента
            assistant_message.content = result.get("answer", "Произошла ошибка при обработке запроса")
            db.commit()
            
            # Отправляем финальный статус
            await websocket.send_json({
                "type": "assistant_message_completed",
                "message_id": str(assistant_message.id)
            })
            
        finally:
            db.close()
            
    except WebSocketDisconnect:
        logger.info(f"WebSocket соединение разорвано: {client_id}")
        await disconnect_websocket(client_id)
    except Exception as e:
        logger.error(f"Ошибка в обработке WebSocket: {str(e)}")
        try:
            await websocket.send_json({
                "type": "error",
                "content": f"Произошла ошибка: {str(e)}"
            })
        except:
            pass
        finally:
            await disconnect_websocket(client_id)
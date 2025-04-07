from typing import List, Dict, Any, Optional
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
import uuid

from app.db.models import Conversation, Message, AgentLog
from app.core.config import settings

class ChatService:
    def __init__(self):
        self.coordinator = None
        self.legal_norms = None
        self.judicial = None
        self.analytics = None
        self.document_prep = None
        self.document_analysis = None

    async def get_user_conversations(self, user_id: uuid.UUID, db: AsyncSession) -> List[Dict[str, Any]]:
        result = await db.execute(
            select(Conversation)
            .where(Conversation.user_id == user_id)
            .order_by(Conversation.updated_at.desc())
        )
        conversations = result.scalars().all()
        
        return [
            {
                "id": str(conv.id),
                "title": conv.title,
                "created_at": conv.created_at.isoformat(),
                "updated_at": conv.updated_at.isoformat(),
                "share_token": conv.share_token
            }
            for conv in conversations
        ]

    async def get_conversation_messages(
        self,
        conversation_id: uuid.UUID,
        user_id: uuid.UUID,
        db: AsyncSession
    ) -> List[Dict[str, Any]]:
        # Verify conversation belongs to user
        result = await db.execute(
            select(Conversation)
            .where(
                Conversation.id == conversation_id,
                Conversation.user_id == user_id
            )
        )
        conversation = result.scalar_one_or_none()
        
        if not conversation:
            return []
        
        # Get messages
        result = await db.execute(
            select(Message)
            .where(Message.conversation_id == conversation_id)
            .order_by(Message.created_at.asc())
        )
        messages = result.scalars().all()
        
        return [
            {
                "id": str(msg.id),
                "content": msg.content,
                "type": msg.type.value,
                "created_at": msg.created_at.isoformat(),
                "likes": msg.likes,
                "dislikes": msg.dislikes,
                "attachments": [
                    {
                        "id": str(att.id),
                        "file_name": att.file_name,
                        "file_type": att.file_type
                    }
                    for att in msg.attachments
                ]
            }
            for msg in messages
        ]

    async def create_message(
        self,
        conversation_id: uuid.UUID,
        content: str,
        message_type: str,
        db: AsyncSession
    ) -> Dict[str, Any]:
        message = Message(
            conversation_id=conversation_id,
            content=content,
            type=message_type
        )
        
        db.add(message)
        await db.commit()
        await db.refresh(message)
        
        return {
            "id": str(message.id),
            "content": message.content,
            "type": message.type.value,
            "created_at": message.created_at.isoformat(),
            "likes": message.likes,
            "dislikes": message.dislikes,
            "attachments": []
        }

    async def log_agent_action(
        self,
        message_id: uuid.UUID,
        agent_type: str,
        action: str,
        details: str,
        db: AsyncSession
    ) -> None:
        log = AgentLog(
            message_id=message_id,
            agent_type=agent_type,
            action=action,
            details=details
        )
        
        db.add(log)
        await db.commit()

chat_service = ChatService() 
from typing import Dict, Any, List, Optional, Union
import logging
import asyncio
import uuid
from datetime import datetime
from sqlalchemy.orm import Session
from app.core.database import get_db
from app.db.models import Conversation, Message, AgentLog
from app.agents.coordinator import coordinator_agent
from app.agents.legal_norms import legal_norms_agent
from app.agents.judicial import judicial_practice_agent
from app.agents.analytics import analytics_agent
from app.agents.document_prep import document_prep_agent

logger = logging.getLogger(__name__)

class ChatService:
    """
    Service for managing chat interactions with the LawGPT system
    """
    
    async def process_message(self, user_id: uuid.UUID, conversation_id: Optional[uuid.UUID], 
                         message_content: str, db: Session) -> Dict[str, Any]:
        """
        Process a user message and generate a response using the multi-agent system
        """
        # Create or get conversation
        if not conversation_id:
            # Create new conversation with title from the first few words of the message
            title = message_content[:30] + "..." if len(message_content) > 30 else message_content
            conversation = Conversation(user_id=user_id, title=title)
            db.add(conversation)
            db.commit()
            db.refresh(conversation)
            conversation_id = conversation.id
        else:
            conversation = db.query(Conversation).filter(Conversation.id == conversation_id).first()
            if not conversation:
                return {"error": "Conversation not found"}
            
            # Update conversation timestamp
            conversation.last_message_at = datetime.now()
            db.commit()
        
        # Create user message
        user_message = Message(
            conversation_id=conversation_id,
            is_user=True,
            content=message_content
        )
        db.add(user_message)
        db.commit()
        db.refresh(user_message)
        
        # Create assistant message (initially empty)
        assistant_message = Message(
            conversation_id=conversation_id,
            is_user=False,
            content=""
        )
        db.add(assistant_message)
        db.commit()
        db.refresh(assistant_message)
        
        # Create coordinator agent log
        coordinator_log = AgentLog(
            message_id=assistant_message.id,
            agent_type="coordinator",
            processing_status="queued"
        )
        db.add(coordinator_log)
        db.commit()
        
        # Start async processing
        asyncio.create_task(self._process_message_async(
            user_id, 
            conversation_id, 
            message_content, 
            assistant_message.id, 
            coordinator_log.id,
            db
        ))
        
        return {
            "conversation_id": conversation_id,
            "message_id": assistant_message.id,
            "status": "processing"
        }
    
    async def _process_message_async(self, user_id: uuid.UUID, conversation_id: uuid.UUID, 
                               message_content: str, assistant_message_id: uuid.UUID,
                               coordinator_log_id: uuid.UUID, db: Session) -> None:
        """
        Asynchronously process a message using the multi-agent system
        """
        db_for_task = next(get_db())  # Get a new DB session for this async task
        
        try:
            # Update coordinator status
            coordinator_log = db_for_task.query(AgentLog).filter(AgentLog.id == coordinator_log_id).first()
            coordinator_log.processing_status = "processing"
            db_for_task.commit()
            
            # Analyze query with coordinator agent
            analysis = await coordinator_agent.analyze_query(message_content)
            
            if "error" in analysis:
                # Handle error
                coordinator_log.processing_status = "error"
                coordinator_log.agent_output = str(analysis["error"])
                db_for_task.commit()
                
                # Update assistant message
                assistant_message = db_for_task.query(Message).filter(Message.id == assistant_message_id).first()
                assistant_message.content = f"Извините, произошла ошибка при обработке вашего запроса: {analysis['error']}"
                db_for_task.commit()
                return
            
            # Update coordinator log with analysis
            coordinator_log.agent_output = str(analysis)
            coordinator_log.processing_status = "completed"
            db_for_task.commit()
            
            # Process with each agent as needed
            agent_responses = {}
            
            # Update assistant message with interim update
            assistant_message = db_for_task.query(Message).filter(Message.id == assistant_message_id).first()
            assistant_message.content = "⏳ Анализ запроса...\n\n"
            
            if "clarifying_questions" in analysis and analysis["clarifying_questions"]:
                assistant_message.content += "Для более точного ответа, пожалуйста, уточните:\n"
                for question in analysis["clarifying_questions"]:
                    assistant_message.content += f"- {question}\n"
                assistant_message.content += "\nПродолжаю анализ на основе имеющейся информации..."
                db_for_task.commit()
            
            # Process with requested agents
            agents_to_use = analysis.get("agents", [])
            
            for agent_name in agents_to_use:
                # Create agent log
                agent_log = AgentLog(
                    message_id=assistant_message_id,
                    agent_type=agent_name,
                    processing_status="processing"
                )
                db_for_task.add(agent_log)
                db_for_task.commit()
                
                # Update assistant message
                assistant_message.content += f"\n\n⏳ Запрос к агенту: {agent_name}..."
                db_for_task.commit()
                
                # Process with appropriate agent
                try:
                    if agent_name == "legal_norms_agent":
                        response = await legal_norms_agent.process_query(message_content)
                    elif agent_name == "judicial_practice_agent":
                        response = await judicial_practice_agent.process_query(message_content)
                    elif agent_name == "analytics_agent":
                        response = await analytics_agent.process_query(message_content)
                    elif agent_name == "document_prep_agent":
                        response = await document_prep_agent.process_query(message_content)
                    else:
                        response = {"error": f"Unknown agent: {agent_name}"}
                    
                    agent_responses[agent_name] = response
                    
                    # Update agent log
                    agent_log.agent_output = str(response)
                    agent_log.processing_status = "completed"
                    db_for_task.commit()
                    
                    # Update assistant message
                    assistant_message.content += " ✓"
                    db_for_task.commit()
                    
                except Exception as e:
                    logger.error(f"Error processing with agent {agent_name}: {str(e)}")
                    agent_log.processing_status = "error"
                    agent_log.agent_output = str(e)
                    db_for_task.commit()
                    
                    assistant_message.content += f" ❌ (Ошибка: {str(e)})"
                    db_for_task.commit()
            
            # Synthesize final response
            assistant_message.content += "\n\n⏳ Формирование итогового ответа..."
            db_for_task.commit()
            
            final_response = await coordinator_agent.synthesize_response(message_content, agent_responses)
            
            # Update the assistant message with the final response
            assistant_message.content = final_response
            db_for_task.commit()
            
        except Exception as e:
            logger.error(f"Error in _process_message_async: {str(e)}")
            
            # Update coordinator log
            coordinator_log = db_for_task.query(AgentLog).filter(AgentLog.id == coordinator_log_id).first()
            coordinator_log.processing_status = "error"
            coordinator_log.agent_output = str(e)
            db_for_task.commit()
            
            # Update assistant message
            assistant_message = db_for_task.query(Message).filter(Message.id == assistant_message_id).first()
            assistant_message.content = f"Извините, произошла ошибка при обработке вашего запроса: {str(e)}"
            db_for_task.commit()
        finally:
            db_for_task.close()
    
    def get_conversation_messages(self, conversation_id: uuid.UUID, db: Session) -> List[Dict[str, Any]]:
        """
        Get all messages in a conversation
        """
        messages = db.query(Message).filter(Message.conversation_id == conversation_id).order_by(Message.created_at).all()
        
        return [
            {
                "id": str(message.id),
                "is_user": message.is_user,
                "content": message.content,
                "created_at": message.created_at.isoformat(),
                "likes": message.likes,
                "dislikes": message.dislikes
            }
            for message in messages
        ]
    
    def get_user_conversations(self, user_id: uuid.UUID, db: Session) -> List[Dict[str, Any]]:
        """
        Get all conversations for a user
        """
        conversations = db.query(Conversation).filter(Conversation.user_id == user_id).order_by(Conversation.last_message_at.desc()).all()
        
        return [
            {
                "id": str(conversation.id),
                "title": conversation.title,
                "created_at": conversation.created_at.isoformat(),
                "last_message_at": conversation.last_message_at.isoformat()
            }
            for conversation in conversations
        ]

# Create singleton instance
chat_service = ChatService()
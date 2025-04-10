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
    
    async def process_message_stream(
        self, 
        user_id: uuid.UUID, 
        conversation_id: uuid.UUID, 
        message_content: str, 
        websocket = None
    ) -> Dict[str, Any]:
        """
        Обрабатывает сообщение пользователя с потоковой передачей промежуточных результатов
        """
        db = next(get_db())
        
        try:
            # Обновляем timestamp беседы
            conversation = db.query(Conversation).filter(
                Conversation.id == conversation_id
            ).first()
            
            if not conversation:
                if websocket:
                    await websocket.send_json({
                        "type": "error",
                        "content": "Беседа не найдена"
                    })
                return {"error": "Беседа не найдена"}
            
            # Обновляем метку времени
            conversation.last_message_at = datetime.now()
            db.commit()
            
            # Создаем сообщение пользователя
            user_message = Message(
                conversation_id=conversation_id,
                is_user=True,
                content=message_content
            )
            db.add(user_message)
            db.commit()
            
            # Создаем сообщение ассистента (изначально пустое)
            assistant_message = Message(
                conversation_id=conversation_id,
                is_user=False,
                content=""
            )
            db.add(assistant_message)
            db.commit()
            
            # Отправляем подтверждение создания сообщений
            if websocket:
                await websocket.send_json({
                    "type": "message_created",
                    "user_message_id": str(user_message.id),
                    "assistant_message_id": str(assistant_message.id)
                })
            
            # Делегируем запрос координатору агентов
            if websocket:
                await websocket.send_json({
                    "type": "thinking", 
                    "content": "Анализирую запрос..."
                })
            
            # Анализируем запрос, чтобы определить нужных агентов
            coordinator = coordinator_agent
            agent_analysis = await coordinator.analyze_query(message_content)
            
            if "error" in agent_analysis:
                error_msg = f"Ошибка анализа запроса: {agent_analysis['error']}"
                assistant_message.content = error_msg
                db.commit()
                
                if websocket:
                    await websocket.send_json({
                        "type": "error",
                        "content": error_msg
                    })
                
                return {"error": error_msg}
            
            # Отправляем информацию о планируемых агентах
            if websocket:
                await websocket.send_json({
                    "type": "thinking",
                    "content": f"План: {agent_analysis.get('plan', '')}\n" +
                            f"Агенты: {', '.join(agent_analysis.get('agents', []))}"
                })
            
            # Выполняем запросы к агентам
            agent_responses = {}
            for agent_name in agent_analysis.get("agents", []):
                if websocket:
                    await websocket.send_json({
                        "type": "thinking",
                        "content": f"Запрос к агенту: {agent_name}..."
                    })
                
                # Вызываем соответствующего агента
                try:
                    if agent_name == "legal_norms_agent":
                        response = await legal_norms_agent.process_query(message_content)
                    elif agent_name == "judicial_practice_agent":
                        response = await judicial_practice_agent.process_query(message_content)
                    elif agent_name == "analytics_agent":
                        response = await analytics_agent.process_query(message_content)
                    elif agent_name == "document_prep_agent":
                        response = await document_prep_agent.process_query(message_content)
                    elif agent_name == "document_analysis_agent":
                        response = await document_analysis_agent.process_query(message_content)
                    else:
                        response = {"error": f"Неизвестный агент: {agent_name}"}
                    
                    agent_responses[agent_name] = response
                    
                    if websocket:
                        if "error" in response:
                            await websocket.send_json({
                                "type": "thinking",
                                "content": f"❌ Ошибка агента {agent_name}: {response['error']}"
                            })
                        else:
                            await websocket.send_json({
                                "type": "thinking",
                                "content": f"✅ Агент {agent_name} завершил работу успешно"
                            })
                except Exception as e:
                    error_msg = f"Ошибка при вызове агента {agent_name}: {str(e)}"
                    agent_responses[agent_name] = {"error": error_msg}
                    
                    if websocket:
                        await websocket.send_json({
                            "type": "thinking",
                            "content": f"❌ {error_msg}"
                        })
            
            # Синтезируем финальный ответ
            if websocket:
                await websocket.send_json({
                    "type": "thinking",
                    "content": "Синтезирую финальный ответ..."
                })
            
            final_response = await coordinator.synthesize_response(
                message_content, 
                agent_responses,
                agent_analysis
            )
            
            # Сохраняем ответ в базу данных
            assistant_message.content = final_response.get("answer", "Ошибка при формировании ответа")
            db.commit()
            
            # Отправляем финальный ответ
            if websocket:
                await websocket.send_json({
                    "type": "answer",
                    "content": final_response.get("answer", ""),
                    "reasoning": final_response.get("reasoning", ""),
                    "message_id": str(assistant_message.id)
                })
            
            return {
                "conversation_id": str(conversation_id),
                "assistant_message_id": str(assistant_message.id),
                "answer": final_response.get("answer", ""),
                "reasoning": final_response.get("reasoning", "")
            }
        except Exception as e:
            logger.error(f"Ошибка при обработке сообщения: {str(e)}")
            
            if websocket:
                await websocket.send_json({
                    "type": "error",
                    "content": f"Произошла ошибка при обработке запроса: {str(e)}"
                })
            
            return {"error": str(e)}
        finally:
            db.close()
    
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
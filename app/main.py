from fastapi import FastAPI, Depends, HTTPException, Query, WebSocket, WebSocketDisconnect, UploadFile, File, Form, Request, BackgroundTasks, status
from fastapi import WebSocket, WebSocketDisconnect, Depends, BackgroundTasks
from app.api.websockets import connect_websocket, disconnect_websocket, handle_websocket_chat
from app.core.security import get_current_user_ws
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.security import OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Session
from sqlalchemy import select
from typing import List, Dict, Any, Optional
import uuid
import json
import logging
import os
from datetime import datetime, timedelta
from fastapi.templating import Jinja2Templates
import secrets
from starlette.middleware.sessions import SessionMiddleware
from starlette.middleware.base import BaseHTTPMiddleware
from pydantic import BaseModel

from app.core.config import settings
from app.core.database import get_db, Base, engine, async_session
from app.core.security import create_access_token, verify_password, get_password_hash
from app.db.models import User, Conversation, Message, AgentLog, Document, Feedback, TempUser, PasswordReset
from app.services.chat import chat_service
from app.services.document import document_service
from app.services.voice import voice_service
from app.api.endpoints import voice
from app.schemas.user import UserCreate, UserLogin, VerifyRequest, PasswordResetRequest, PasswordResetConfirm
from app.utils.mail import send_verification_email, send_recovery_email
from app.api import chat, auth
from app.api.auth import get_current_user

# Constants
ALGORITHM = "HS256"

# Logging setup
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(title=settings.PROJECT_NAME)

# Create database tables if they don't exist
async def init_db():
    logger.info("Starting database initialization...")
    try:
        async with engine.begin() as conn:
            logger.info("Dropping all tables...")
            await conn.run_sync(Base.metadata.drop_all)
            logger.info("Creating all tables...")
            await conn.run_sync(Base.metadata.create_all)
        
        logger.info("Creating test user...")
        # Создаем тестового пользователя в отдельной сессии
        async with async_session() as session:
            try:
                # Проверяем, существует ли уже пользователь
                result = await session.execute(
                    select(User).where(User.email == "s9003259988@gmail.com")
                )
                user = result.scalar_one_or_none()
                
                if not user:
                    logger.info("Test user not found, creating new one...")
                    # Создаем нового пользователя
                    user = User(
                        email="s9003259988@gmail.com",
                        hashed_password=get_password_hash("password"),
                        is_active=True,
                        is_verified=True,
                        first_name="Test",
                        last_name="User"
                    )
                    session.add(user)
                    await session.commit()
                    logger.info("Test user created successfully")
                else:
                    logger.info("Test user already exists")
                
            except Exception as e:
                logger.error(f"Error creating test user: {str(e)}")
                await session.rollback()
                raise
            finally:
                await session.close()
                
        logger.info("Database initialization completed")
        
    except Exception as e:
        logger.error(f"Error during database initialization: {str(e)}")
        raise

# Initialize database tables
@app.on_event("startup")
async def startup_event():
    logger.info("Application startup event triggered")
    try:
        await init_db()
        logger.info("Database initialization successful")
    except Exception as e:
        logger.error(f"Failed to initialize database: {str(e)}")
        raise

# Mount static files
app.mount("/static", StaticFiles(directory="app/static"), name="static")

# Templates
templates = Jinja2Templates(directory="app/templates")

# Add middleware in correct order
# 1. Session middleware first
app.add_middleware(
    SessionMiddleware,
    secret_key=settings.SECRET_KEY,
    session_cookie="session",
    same_site="lax",
    https_only=False
)

# 2. CSRF middleware second
class CSRFMiddleware(BaseHTTPMiddleware):
    async def dispatch(self, request: Request, call_next):
        # Пропускаем проверку для логина полностью
        if request.url.path == "/api/auth/login":
            return await call_next(request)
            
        if request.method in ["POST", "PUT", "DELETE", "PATCH"]:
            try:
                csrf_token = request.headers.get("X-CSRF-TOKEN")
                session = request.session
                session_token = session.get("csrf_token") if session else None
                
                logger.info(f"Request path: {request.url.path}")
                logger.info(f"Request headers: {request.headers}")
                logger.info(f"Request CSRF token: {csrf_token}")
                logger.info(f"Session CSRF token: {session_token}")
                logger.info(f"Session data: {dict(session) if session else None}")
                
                if not session:
                    logger.error("No session found")
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "No session found"}
                    )
                
                if not csrf_token or not session_token or csrf_token != session_token:
                    logger.error("CSRF token validation failed")
                    return JSONResponse(
                        status_code=403,
                        content={"detail": "CSRF token missing or invalid"}
                    )
            except Exception as e:
                logger.error(f"Error in CSRF validation: {str(e)}")
                return JSONResponse(
                    status_code=500,
                    content={"detail": f"Internal server error during CSRF validation: {str(e)}"}
                )
        
        response = await call_next(request)
        return response

app.add_middleware(CSRFMiddleware)

# 3. CORS middleware last
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*", "X-CSRF-TOKEN"],
    expose_headers=["*"]
)

# Include routers
app.include_router(auth.router, prefix="/api/auth", tags=["auth"])
app.include_router(chat.router, prefix="/api/chat", tags=["chat"])
app.include_router(voice.router, prefix="/api/voice", tags=["voice"])

# WebSocket connections
active_connections: Dict[uuid.UUID, WebSocket] = {}

@app.get("/", response_class=HTMLResponse)
async def read_root(request: Request):
    # Generate CSRF token if not exists
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_hex(32)
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "csrf_token": request.session["csrf_token"]
        }
    )

@app.get("/{full_path:path}", response_class=HTMLResponse)
async def catch_all(request: Request, full_path: str):
    # Generate CSRF token if not exists
    if "csrf_token" not in request.session:
        request.session["csrf_token"] = secrets.token_hex(32)
    
    return templates.TemplateResponse(
        "index.html",
        {
            "request": request,
            "csrf_token": request.session["csrf_token"]
        }
    )

# Ensure uploads directory exists
os.makedirs(settings.UPLOAD_DIR, exist_ok=True)

# WebSocket endpoint
@app.websocket("/ws/{client_id}")
async def websocket_endpoint(websocket: WebSocket, client_id: str):
    await websocket.accept()
    
    # Store connection
    client_uuid = uuid.UUID(client_id)
    active_connections[client_uuid] = websocket
    
    try:
        while True:
            # Keep connection alive
            data = await websocket.receive_text()
            
            # Echo back
            await websocket.send_text(f"Echo: {data}")
    except WebSocketDisconnect:
        # Remove connection
        if client_uuid in active_connections:
            del active_connections[client_uuid]

@app.post("/api/v1/users/register")
async def register_user(email: str = Form(...), password: str = Form(...), db: AsyncSession = Depends(get_db)):
    # Check if user already exists
    result = await db.execute(f"SELECT * FROM users WHERE email = '{email}'")
    existing_user = result.first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Email already registered")
    
    # Create new user
    user = User(
        email=email,
        hashed_password=get_password_hash(password),
        is_active=True,
        is_verified=True
    )
    
    db.add(user)
    await db.commit()
    await db.refresh(user)
    
    # Create access token
    access_token_expires = timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        subject=str(user.id), expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@app.get("/api/v1/users/me")
async def read_users_me(current_user: User = Depends(auth.get_current_user)):
    return {
        "id": str(current_user.id),
        "email": current_user.email,
        "is_active": current_user.is_active,
        "is_superuser": current_user.is_superuser,
        "is_verified": current_user.is_verified,
        "created_at": current_user.created_at.isoformat()
    }

@app.get("/api/v1/conversations")
async def get_conversations(current_user: User = Depends(auth.get_current_user), db: AsyncSession = Depends(get_db)):
    return chat_service.get_user_conversations(current_user.id, db)

@app.post("/api/v1/conversations")
async def create_conversation(current_user: User = Depends(auth.get_current_user), db: AsyncSession = Depends(get_db)):
    conversation = Conversation(
        user_id=current_user.id,
        title=f"Новый чат {datetime.now().strftime('%d.%m.%Y %H:%M')}"
    )
    
    db.add(conversation)
    await db.commit()
    await db.refresh(conversation)
    
    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "created_at": conversation.created_at.isoformat(),
        "last_message_at": conversation.last_message_at.isoformat()
    }

@app.get("/api/v1/conversations/{conversation_id}")
async def get_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    conversation = await db.execute(f"SELECT * FROM conversations WHERE id = '{conversation_id}' AND user_id = '{current_user.id}'")
    conversation = conversation.first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "created_at": conversation.created_at.isoformat(),
        "last_message_at": conversation.last_message_at.isoformat(),
        "messages": chat_service.get_conversation_messages(conversation.id, db)
    }

@app.post("/api/v1/conversations/{conversation_id}/messages")
async def create_message(
    conversation_id: uuid.UUID,
    message_content: str = Form(...),
    current_user: User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify conversation belongs to user
    conversation = await db.execute(f"SELECT * FROM conversations WHERE id = '{conversation_id}' AND user_id = '{current_user.id}'")
    conversation = conversation.first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Process message
    result = await chat_service.process_message(
        current_user.id,
        conversation_id,
        message_content,
        db
    )
    
    return result

@app.post("/api/v1/conversations/{conversation_id}/voice")
async def upload_voice_message(
    conversation_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify conversation belongs to user
    conversation = await db.execute(f"SELECT * FROM conversations WHERE id = '{conversation_id}' AND user_id = '{current_user.id}'")
    conversation = conversation.first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Transcribe audio
    transcription = await voice_service.transcribe_audio(file)
    
    if "error" in transcription:
        raise HTTPException(status_code=400, detail=transcription["error"])
    
    # Process transcribed message
    result = await chat_service.process_message(
        current_user.id,
        conversation_id,
        transcription["text"],
        db
    )
    
    return {
        **result,
        "transcription": transcription["text"]
    }

@app.post("/api/v1/conversations/{conversation_id}/attachments")
async def upload_attachment(
    conversation_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify conversation belongs to user
    conversation = await db.execute(f"SELECT * FROM conversations WHERE id = '{conversation_id}' AND user_id = '{current_user.id}'")
    conversation = conversation.first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Check file size
    file_size = 0
    content = await file.read()
    file_size = len(content)
    await file.seek(0)  # Reset file position
    
    if file_size > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="File too large")
    
    # Create a message for the attachment
    message = Message(
        conversation_id=conversation_id,
        is_user=True,
        content=f"[Attached file: {file.filename}]"
    )
    
    db.add(message)
    await db.commit()
    await db.refresh(message)
    
    # Create attachment
    from app.db.models import Attachment
    
    # Save file
    file_path = os.path.join(settings.UPLOAD_DIR, f"{uuid.uuid4()}_{file.filename}")
    with open(file_path, "wb") as f:
        f.write(content)
    
    attachment = Attachment(
        message_id=message.id,
        file_name=file.filename,
        file_type=file.content_type,
        file_size=file_size,
        storage_path=file_path
    )
    
    db.add(attachment)
    await db.commit()
    
    return {
        "message_id": str(message.id),
        "attachment_id": str(attachment.id),
        "file_name": attachment.file_name,
        "file_size": attachment.file_size
    }

@app.post("/api/v1/messages/{message_id}/feedback")
async def add_feedback(
    message_id: uuid.UUID,
    feedback_type: str = Form(...),  # 'like' or 'dislike'
    current_user: User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify message exists
    message = await db.execute(f"SELECT * FROM messages WHERE id = '{message_id}'")
    message = message.first()
    
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Verify conversation belongs to user
    conversation = await db.execute(f"SELECT * FROM conversations WHERE id = '{message.conversation_id}' AND user_id = '{current_user.id}'")
    conversation = conversation.first()
    
    if not conversation:
        raise HTTPException(status_code=403, detail="Not authorized to provide feedback for this message")
    
    # Check if feedback already exists
    existing_feedback = await db.execute(f"SELECT * FROM feedback WHERE message_id = '{message_id}' AND user_id = '{current_user.id}'")
    existing_feedback = existing_feedback.first()
    
    if existing_feedback:
        # Update existing feedback
        existing_feedback.feedback_type = feedback_type
        await db.commit()
    else:
        # Create new feedback
        feedback = Feedback(
            message_id=message_id,
            user_id=current_user.id,
            feedback_type=feedback_type
        )
        
        db.add(feedback)
        await db.commit()
    
    # Update message likes/dislikes count
    likes = await db.execute(f"SELECT COUNT(*) FROM feedback WHERE message_id = '{message_id}' AND feedback_type = 'like'")
    likes = likes.first()[0]
    
    dislikes = await db.execute(f"SELECT COUNT(*) FROM feedback WHERE message_id = '{message_id}' AND feedback_type = 'dislike'")
    dislikes = dislikes.first()[0]
    
    message.likes = likes
    message.dislikes = dislikes
    await db.commit()
    
    return {
        "message_id": str(message_id),
        "feedback_type": feedback_type,
        "likes": likes,
        "dislikes": dislikes
    }

@app.post("/api/v1/documents/generate")
async def generate_document(
    message_id: uuid.UUID = Form(...),
    query: str = Form(...),
    parameters: str = Form(...),  # JSON string
    current_user: User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify message exists
    message = await db.execute(f"SELECT * FROM messages WHERE id = '{message_id}'")
    message = message.first()
    
    if not message:
        raise HTTPException(status_code=404, detail="Message not found")
    
    # Verify conversation belongs to user
    conversation = await db.execute(f"SELECT * FROM conversations WHERE id = '{message.conversation_id}' AND user_id = '{current_user.id}'")
    conversation = conversation.first()
    
    if not conversation:
        raise HTTPException(status_code=403, detail="Not authorized to generate documents for this message")
    
    # Parse parameters
    try:
        params = json.loads(parameters)
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid parameters format")
    
    # Generate document
    result = await document_service.generate_document(message_id, query, params, db)
    
    return result

@app.get("/api/v1/documents/{document_id}")
async def get_document(
    document_id: uuid.UUID,
    current_user: User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Get document
    document = document_service.get_document(document_id, db)
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Verify document belongs to user
    message = await db.execute(f"SELECT * FROM messages WHERE id = '{uuid.UUID(document['message_id'])}'")
    message = message.first()
    conversation = await db.execute(f"SELECT * FROM conversations WHERE id = '{message.conversation_id}' AND user_id = '{current_user.id}'")
    conversation = conversation.first()
    
    if not conversation:
        raise HTTPException(status_code=403, detail="Not authorized to access this document")
    
    return document

@app.get("/api/v1/documents/shared/{share_token}")
async def get_shared_document(
    share_token: str,
    db: AsyncSession = Depends(get_db)
):
    # Get document
    document = document_service.get_document_by_token(share_token, db)
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    return document

@app.get("/api/v1/documents/{document_id}/download")
async def download_document(
    document_id: uuid.UUID,
    current_user: User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Get document
    document = document_service.get_document(document_id, db)
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Verify document belongs to user
    message = await db.execute(f"SELECT * FROM messages WHERE id = '{uuid.UUID(document['message_id'])}'")
    message = message.first()
    conversation = await db.execute(f"SELECT * FROM conversations WHERE id = '{message.conversation_id}' AND user_id = '{current_user.id}'")
    conversation = conversation.first()
    
    if not conversation:
        raise HTTPException(status_code=403, detail="Not authorized to access this document")
    
    # Create DOCX file
    file_path = document_service.create_docx(document_id, db)
    
    if not file_path:
        raise HTTPException(status_code=500, detail="Error creating DOCX file")
    
    return FileResponse(
        path=file_path,
        filename=f"{document['title']}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

@app.get("/api/v1/documents/shared/{share_token}/download")
async def download_shared_document(
    share_token: str,
    db: AsyncSession = Depends(get_db)
):
    # Get document
    document = await db.execute(f"SELECT * FROM documents WHERE share_token = '{share_token}'")
    document = document.first()
    
    if not document:
        raise HTTPException(status_code=404, detail="Document not found")
    
    # Create DOCX file
    file_path = document_service.create_docx(document.id, db)
    
    if not file_path:
        raise HTTPException(status_code=500, detail="Error creating DOCX file")
    
    return FileResponse(
        path=file_path,
        filename=f"{document.title}.docx",
        media_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document"
    )

@app.post("/api/v1/conversations/{conversation_id}/share")
async def share_conversation(
    conversation_id: uuid.UUID,
    current_user: User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Verify conversation belongs to user
    conversation = await db.execute(f"SELECT * FROM conversations WHERE id = '{conversation_id}' AND user_id = '{current_user.id}'")
    conversation = conversation.first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    # Generate share token if not already exists
    if not conversation.share_token:
        from app.core.security import generate_share_token
        conversation.share_token = generate_share_token()
        await db.commit()
    
    return {
        "conversation_id": str(conversation.id),
        "share_token": conversation.share_token,
        "share_url": f"/shared/conversation/{conversation.share_token}"
    }

@app.get("/api/v1/conversations/shared/{share_token}")
async def get_shared_conversation(
    share_token: str,
    db: AsyncSession = Depends(get_db)
):
    # Get conversation
    conversation = await db.execute(f"SELECT * FROM conversations WHERE share_token = '{share_token}'")
    conversation = conversation.first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    
    return {
        "id": str(conversation.id),
        "title": conversation.title,
        "created_at": conversation.created_at.isoformat(),
        "last_message_at": conversation.last_message_at.isoformat(),
        "messages": chat_service.get_conversation_messages(conversation.id, db)
    }

@app.post("/api/v1/conversations/{conversation_id}/document")
async def upload_document_image(
    conversation_id: uuid.UUID,
    file: UploadFile = File(...),
    current_user: User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Проверяем, принадлежит ли беседа пользователю
    conversation = await db.execute(f"SELECT * FROM conversations WHERE id = '{conversation_id}' AND user_id = '{current_user.id}'")
    conversation = conversation.first()
    
    if not conversation:
        raise HTTPException(status_code=404, detail="Беседа не найдена")
    
    # Проверяем размер и тип файла
    file_size = 0
    content = await file.read()
    file_size = len(content)
    await file.seek(0)  # Сбрасываем позицию файла
    
    if file_size > settings.MAX_UPLOAD_SIZE:
        raise HTTPException(status_code=400, detail="Файл слишком большой")
    
    if not file.content_type.startswith("image/"):
        raise HTTPException(status_code=400, detail="Файл должен быть изображением")
    
    # Сохраняем изображение
    file_path = os.path.join(settings.UPLOAD_DIR, f"{uuid.uuid4()}_{file.filename}")
    with open(file_path, "wb") as f:
        f.write(content)
    
    # Создаем сообщение для вложения
    message = Message(
        conversation_id=conversation_id,
        is_user=True,
        content=f"[Документ: {file.filename}]"
    )
    
    db.add(message)
    await db.commit()
    await db.refresh(message)
    
    # Создаем вложение
    from app.db.models import Attachment
    
    attachment = Attachment(
        message_id=message.id,
        file_name=file.filename,
        file_type=file.content_type,
        file_size=file_size,
        storage_path=file_path
    )
    
    db.add(attachment)
    await db.commit()
    
    # Получаем публичный URL для изображения
    image_url = f"{settings.BASE_URL}/uploads/{os.path.basename(file_path)}"
    
    # Обрабатываем изображение с помощью агента анализа документов
    result = await chat_service.process_image_message(
        user_id=current_user.id,
        conversation_id=conversation_id,
        image_url=image_url,
        db=db
    )
    
    return {
        "message_id": str(message.id),
        "attachment_id": str(attachment.id),
        "file_name": attachment.file_name,
        "file_size": attachment.file_size,
        "analysis_status": result.get("status", "обработка")
    }

# WebSocket эндпоинты
@app.websocket("/ws/chat/{client_id}")
async def websocket_chat_endpoint(
    websocket: WebSocket, 
    client_id: str,
    conversation_id: Optional[str] = None
):
    """WebSocket эндпоинт для чата с потоковой передачей"""
    await connect_websocket(websocket, client_id)
    
    try:
        # Аутентификация через токен
        user = await get_current_user_ws(websocket)
        
        # Обработка сообщений чата
        await handle_websocket_chat(
            websocket, 
            client_id, 
            user, 
            uuid.UUID(conversation_id) if conversation_id else None
        )
    except Exception as e:
        logger.error(f"Ошибка в WebSocket: {str(e)}")
        try:
            await websocket.send_json({"type": "error", "message": str(e)})
        except:
            pass
    finally:
        await disconnect_websocket(client_id)



@app.get("/api/v1/messages/{message_id}")
async def get_message_status(
    message_id: uuid.UUID,
    current_user: User = Depends(auth.get_current_user),
    db: AsyncSession = Depends(get_db)
):
    # Получаем сообщение
    message = await db.execute(f"SELECT * FROM messages WHERE id = '{message_id}'")
    message = message.first()
    
    if not message:
        raise HTTPException(status_code=404, detail="Сообщение не найдено")
    
    # Проверяем, принадлежит ли сообщение пользователю через беседу
    conversation = await db.execute(f"SELECT * FROM conversations WHERE id = '{message.conversation_id}' AND user_id = '{current_user.id}'")
    conversation = conversation.first()
    
    if not conversation:
        raise HTTPException(status_code=403, detail="Нет доступа к этому сообщению")
    
    # Получаем логи агентов для этого сообщения
    agent_logs = await db.execute(f"SELECT * FROM agent_logs WHERE message_id = '{message_id}' ORDER BY created_at DESC")
    agent_logs = agent_logs.all()
    
    # Определяем статус на основе логов
    status = "completed"
    if any(log.processing_status == "error" for log in agent_logs):
        status = "error"
        error_message = next((log.agent_output for log in agent_logs if log.processing_status == "error"), None)
    elif any(log.processing_status in ["queued", "processing"] for log in agent_logs):
        status = "processing"
    
    return {
        "id": str(message.id),
        "content": message.content,
        "status": status,
        "error": error_message if status == "error" else None,
        "created_at": message.created_at.isoformat()
    }

# Модель для сообщения чата
class ChatMessage(BaseModel):
    message: str
    conversation_id: Optional[uuid.UUID] = None

# Эндпоинт для отправки сообщения
@app.post("/api/chat/send")
async def send_message(
    message: ChatMessage,
    request: Request,
    current_user: User = Depends(auth.get_current_user),
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

if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8000)
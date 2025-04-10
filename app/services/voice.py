from fastapi import APIRouter, UploadFile, File, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
import logging
import asyncio
import uuid
import json
import os
from datetime import datetime

from app.services.voice import voice_service
from app.core.config import settings

router = APIRouter()
logger = logging.getLogger(__name__)

# WebSocket соединения для потоковой передачи аудио
voice_connections = {}

class VoiceService:
    """
    Сервис для транскрибации голосовых сообщений с использованием Whisper
    и управления файлами аудиозаписей
    """
    
    def __init__(self):
        self.upload_dir = os.path.join(settings.UPLOAD_DIR, "voice")
        os.makedirs(self.upload_dir, exist_ok=True)
    
    @router.post("/transcribe")
    async def transcribe_audio(file: UploadFile = File(...)):
        """
        Транскрибирует аудиофайл в текст через Whisper API
        """
        try:
            result = await voice_service.transcribe_audio(file)
            return result
        except Exception as e:
            logger.error(f"Ошибка при транскрибации аудио: {str(e)}")
            raise HTTPException(status_code=500, detail=f"Ошибка при транскрибации аудио: {str(e)}")

    @router.websocket("/ws/voice")
    async def voice_websocket(websocket: WebSocket):
        """
        WebSocket эндпоинт для потоковой передачи аудио
        """
        client_id = str(uuid.uuid4())
        await websocket.accept()
        voice_connections[client_id] = websocket
        
        try:
            # Отправляем клиенту его ID
            await websocket.send_json({"type": "connection", "client_id": client_id})
            
            # Цикл обработки сообщений
            while True:
                message = await websocket.receive()
                
                # Если получены бинарные данные (аудио)
                if "bytes" in message:
                    audio_data = message["bytes"]
                    
                    # Сохраняем аудио во временный файл
                    temp_file_path = f"/tmp/voice_{client_id}.wav"
                    with open(temp_file_path, "wb") as f:
                        f.write(audio_data)
                    
                    # Вызываем транскрибацию
                    try:
                        transcription = await voice_service.transcribe_file(temp_file_path)
                        await websocket.send_json({
                            "type": "transcription",
                            "text": transcription.get("text", ""),
                            "status": "completed"
                        })
                    except Exception as e:
                        await websocket.send_json({
                            "type": "error",
                            "message": f"Ошибка транскрибации: {str(e)}"
                        })
                    finally:
                        # Удаляем временный файл
                        if os.path.exists(temp_file_path):
                            os.remove(temp_file_path)
                
                # Если получено текстовое сообщение
                elif "text" in message:
                    data = json.loads(message["text"])
                    
                    # Обработка команды "stop_recording"
                    if data.get("command") == "stop_recording":
                        await websocket.send_json({
                            "type": "status",
                            "message": "Запись остановлена, обработка аудио..."
                        })
        
        except WebSocketDisconnect:
            logger.info(f"Клиент отключился: {client_id}")
        except Exception as e:
            logger.error(f"Ошибка WebSocket: {str(e)}")
        finally:
            if client_id in voice_connections:
                del voice_connections[client_id]
    
    def save_voice_file(self, file_content: bytes, file_name: str) -> str:
        """
        Сохраняет аудиофайл в директорию uploads/voice
        """
        file_path = os.path.join(self.upload_dir, file_name)
        with open(file_path, "wb") as f:
            f.write(file_content)
        return file_path

    def delete_voice_file(self, file_path: str) -> None:
        """
        Удаляет аудиофайл по указанному пути
        """
        if os.path.exists(file_path):
            os.remove(file_path)

    def get_file_path(self, file_name: str) -> str:
        """
        Возвращает полный путь к файлу
        """
        return os.path.join(self.upload_dir, file_name)

# Создаем экземпляр сервиса
voice_service = VoiceService()
from typing import Dict, Any, Optional
import logging
import httpx
import tempfile
import os
import uuid
from fastapi import UploadFile, HTTPException, File
from fastapi.responses import JSONResponse
from app.core.config import settings
from datetime import datetime

logger = logging.getLogger(__name__)

class VoiceService:
    """
    Сервис для транскрибации голосовых сообщений с использованием Whisper
    и управления файлами аудиозаписей
    """
    
    def __init__(self):
        self.upload_dir = os.path.join(settings.UPLOAD_DIR, "voice")
        os.makedirs(self.upload_dir, exist_ok=True)
    
    async def transcribe_audio(self, file: UploadFile = File(...)):
        """
        Транскрибирует аудиофайл в текст с помощью Whisper API
        """
        try:
            temp_file_path = f"/tmp/{uuid.uuid4()}.wav"
            
            # Сохраняем полученный файл
            with open(temp_file_path, "wb") as buffer:
                buffer.write(await file.read())
            
            async with httpx.AsyncClient() as client:
                files = {"file": (file.filename, open(temp_file_path, "rb"), "audio/wav")}
                headers = {"Accept": "application/json"}
                
                response = await client.post(
                    f"{settings.WHISPER_API_URL}/transcribe",
                    files=files,
                    headers=headers,
                    timeout=30.0  # Увеличенный таймаут для обработки аудио
                )
            
            # Удаляем временный файл
            if os.path.exists(temp_file_path):
                os.remove(temp_file_path)
            
            if response.status_code != 200:
                return JSONResponse(
                    status_code=response.status_code,
                    content={"error": "Ошибка при транскрибации аудио", "details": response.text}
                )
            
            return response.json()
            
        except Exception as e:
            logger.error(f"Ошибка при транскрибации аудио: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Ошибка при транскрибации аудио: {str(e)}"
            )
    
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
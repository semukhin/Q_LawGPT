from fastapi import UploadFile, File, HTTPException
import logging
import os
import aiohttp
import io
import json
from typing import Dict, Any, Optional
import uuid

from app.core.config import settings

logger = logging.getLogger(__name__)

class VoiceService:
    """
    Сервис для транскрибации голосовых сообщений с использованием Whisper
    и управления файлами аудиозаписей
    """
    
    def __init__(self):
        self.upload_dir = os.path.join(settings.UPLOAD_DIR, "voice")
        os.makedirs(self.upload_dir, exist_ok=True)
    
    async def transcribe_audio(self, file: UploadFile) -> Dict[str, Any]:
        """
        Транскрибирует аудиофайл в текст через Whisper API
        """
        try:
            contents = await file.read()
            file_name = f"{uuid.uuid4()}_{file.filename}"
            file_path = self.save_voice_file(contents, file_name)
            
            result = await self.transcribe_file(file_path)
            
            # Удаляем временный файл
            self.delete_voice_file(file_path)
            
            return result
        except Exception as e:
            logger.error(f"Ошибка при транскрибации аудио: {str(e)}")
            return {"error": str(e)}
    
    async def transcribe_file(self, file_path: str) -> Dict[str, Any]:
        """
        Транскрибирует файл, находящийся на диске
        """
        try:
            # Проверяем доступность локального Whisper API
            whisper_url = settings.WHISPER_API_URL
            
            async with aiohttp.ClientSession() as session:
                with open(file_path, "rb") as f:
                    data = aiohttp.FormData()
                    data.add_field('file', 
                                  f,
                                  filename=os.path.basename(file_path),
                                  content_type='audio/wav')
                    
                    async with session.post(whisper_url + "/transcribe", data=data) as response:
                        if response.status != 200:
                            error_text = await response.text()
                            logger.error(f"Whisper API вернул ошибку: {error_text}")
                            return {"error": f"Ошибка Whisper API: {error_text}"}
                        
                        result = await response.json()
                        return result
        except Exception as e:
            logger.error(f"Ошибка при транскрибации файла: {str(e)}")
            return {"error": str(e)}
    
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
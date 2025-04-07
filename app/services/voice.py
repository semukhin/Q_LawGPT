from typing import Dict, Any
import logging
import httpx
import tempfile
import os
from fastapi import UploadFile, HTTPException
from app.core.config import settings

logger = logging.getLogger(__name__)

class VoiceService:
    """
    Сервис для транскрибации голосовых сообщений с использованием Whisper
    """
    
    async def transcribe_audio(self, file: UploadFile) -> Dict[str, Any]:
        """
        Транскрибирует аудиофайл в текст с помощью Whisper API
        """
        try:
            # Сохраняем файл во временную директорию
            with tempfile.NamedTemporaryFile(delete=False, suffix=os.path.splitext(file.filename)[1]) as temp_file:
                content = await file.read()
                temp_file.write(content)
                temp_path = temp_file.name

            try:
                # Отправляем файл в Whisper API
                async with httpx.AsyncClient() as client:
                    files = {"file": ("audio.wav", open(temp_path, "rb"), "audio/wav")}
                    response = await client.post(
                        f"{settings.WHISPER_API_URL}/transcribe",
                        files=files
                    )
                    
                    if response.status_code != 200:
                        logger.error(f"Ошибка Whisper API: {response.text}")
                        raise HTTPException(
                            status_code=response.status_code,
                            detail="Ошибка при транскрибации аудио"
                        )
                    
                    result = response.json()
                    return {
                        "text": result.get("text", ""),
                        "language": "ru"
                    }
                    
            finally:
                # Удаляем временный файл
                try:
                    os.unlink(temp_path)
                except Exception as e:
                    logger.error(f"Ошибка при удалении временного файла: {str(e)}")
                    
        except Exception as e:
            logger.error(f"Ошибка при обработке аудио: {str(e)}")
            raise HTTPException(
                status_code=500,
                detail=f"Ошибка при обработке аудио: {str(e)}"
            )

# Создаем singleton-экземпляр сервиса
voice_service = VoiceService()
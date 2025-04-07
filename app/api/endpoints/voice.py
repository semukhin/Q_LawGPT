from fastapi import APIRouter, UploadFile, File, HTTPException
import httpx
import os
from app.core.config import settings

router = APIRouter()

@router.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Транскрибирует аудиофайл в текст с помощью Whisper API
    """
    try:
        async with httpx.AsyncClient() as client:
            files = {"file": (file.filename, await file.read())}
            response = await client.post(
                f"{settings.WHISPER_API_URL}/transcribe",
                files=files
            )
            
            if response.status_code != 200:
                raise HTTPException(
                    status_code=response.status_code,
                    detail="Ошибка при транскрибации аудио"
                )
                
            return response.json()
            
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при обработке аудио: {str(e)}"
        ) 
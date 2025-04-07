import torch
from fastapi import FastAPI, UploadFile, File, HTTPException
from transformers import WhisperForConditionalGeneration, WhisperProcessor
import io
import librosa
import numpy as np
import os
from app.core.config import settings

app = FastAPI()

# Загрузка модели и процессора
model_id = settings.WHISPER_MODEL
processor = WhisperProcessor.from_pretrained(model_id)
model = WhisperForConditionalGeneration.from_pretrained(model_id)

# Определение устройства
device = "cuda" if torch.cuda.is_available() else "cpu"
print(f"Using device: {device}")
model = model.to(device)

def resample_if_necessary(audio_data, orig_sr):
    """
    Преобразует частоту дискретизации в 16кГц, если она отличается
    """
    target_sr = 16000
    if orig_sr != target_sr:
        audio_data = librosa.resample(
            y=audio_data, 
            orig_sr=orig_sr, 
            target_sr=target_sr
        )
    return audio_data

@app.post("/transcribe")
async def transcribe_audio(file: UploadFile = File(...)):
    """
    Транскрибирует аудиофайл в текст
    """
    try:
        # Чтение аудиофайла
        audio_bytes = await file.read()
        audio_io = io.BytesIO(audio_bytes)
        
        # Загрузка аудио с оригинальной частотой дискретизации
        audio_data, orig_sr = librosa.load(audio_io, sr=None)
        print(f"Оригинальная частота дискретизации: {orig_sr} Гц")
        
        # Преобразование частоты дискретизации если нужно
        audio_data = resample_if_necessary(audio_data, orig_sr)
        
        # Предобработка аудио
        input_features = processor(
            audio_data, 
            sampling_rate=16000, 
            return_tensors="pt"
        ).input_features.to(device)
        
        # Транскрибация
        with torch.no_grad():  # Экономим память
            predicted_ids = model.generate(
                input_features,
                language="russian",
                task="transcribe"
            )
        
        # Декодирование результата
        transcription = processor.batch_decode(
            predicted_ids, 
            skip_special_tokens=True
        )[0]
        
        return {
            "text": transcription,
            "original_sample_rate": orig_sr
        }
        
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Ошибка при обработке аудио: {str(e)}"
        ) 
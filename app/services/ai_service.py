# app/services/ai_service.py
import requests
import json
import logging
from typing import Dict, Any, Optional, List

logger = logging.getLogger(__name__)

def call_qwen_api(
    prompt: str,
    system_message: str = None,
    image_url: str = None,
    api_key: str = None,
    max_tokens: int = 20000,
    temperature: float = 1.0
) -> Dict[str, Any]:
    """
    Единая функция для вызова Qwen API для всех агентов
    
    Параметры:
    - prompt: Текст запроса
    - system_message: Системное сообщение (роль)
    - image_url: URL изображения (если требуется)
    - api_key: API-ключ OpenRouter
    - max_tokens: Максимальное количество токенов в ответе
    - temperature: Температура генерации (0.0-1.0)
    
    Возвращает:
    - Словарь с ответом или информацией об ошибке
    """
    from app.core.config import settings
    
    # Используем ключ из параметров или из настроек
    api_key = api_key or settings.OPENROUTER_API_KEY
    
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": "https://lawgpt.ru",
        "X-Title": "LawGPT.ru"
    }
    
    # Создаем сообщения в зависимости от наличия системного сообщения
    messages = []
    
    if system_message:
        messages.append({"role": "system", "content": system_message})
    
    # Если есть изображение, создаем мультимодальный запрос
    if image_url:
        content = [
            {"type": "text", "text": prompt},
            {"type": "image_url", "image_url": {"url": image_url}}
        ]
        messages.append({"role": "user", "content": content})
    else:
        # Только текстовый запрос
        messages.append({"role": "user", "content": prompt})
    
    payload = {
        "model": "qwen/qwen2.5-vl-72b-instruct:free",
        "messages": messages,
        "max_tokens": max_tokens,
        "temperature": temperature
    }
    
    try:
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
            timeout=30
        )
        response.raise_for_status()
        result = response.json()
        
        if result and "choices" in result and len(result["choices"]) > 0:
            text_response = result["choices"][0]["message"]["content"]
            return {
                "text": text_response,
                "raw_response": result,
                "success": True
            }
        else:
            logger.warning("Неожиданный формат ответа от API")
            return {
                "text": None,
                "raw_response": result,
                "success": False,
                "error": "Неожиданный формат ответа"
            }
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка запроса: {str(e)}")
        return {
            "text": None,
            "success": False,
            "error": str(e)
        }
    except Exception as e:
        logger.error(f"Непредвиденная ошибка: {str(e)}")
        return {
            "text": None,
            "success": False,
            "error": str(e)
        }
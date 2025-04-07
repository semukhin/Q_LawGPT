import requests
import json
import os
import logging
from typing import Dict, Any, Optional

# Настройка логирования
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

def analyze_image(
    api_key: str, 
    image_url: str, 
    prompt: str,
    site_url: str = None, 
    site_name: str = None
) -> Optional[Dict[str, Any]]:
    """
    Анализирует изображение с использованием модели Qwen-VL через OpenRouter API
    
    Параметры:
    - api_key: Ключ API OpenRouter
    - image_url: Публичный URL изображения или строка в формате base64
    - prompt: Текстовый запрос к модели
    - site_url: Опционально - URL вашего сайта
    - site_name: Опционально - название приложения
    
    Возвращает:
    - Словарь с ответом модели или None в случае ошибки
    """
    headers = {
        "Authorization": f"Bearer {api_key}",
        "Content-Type": "application/json",
    }
    
    # Добавляем опциональные заголовки
    if site_url:
        headers["HTTP-Referer"] = site_url
    if site_name:
        headers["X-Title"] = site_name

    payload = {
        "model": "qwen/qwen2.5-vl-72b-instruct:free",
        "messages": [
            {
                "role": "user",
                "content": [
                    {
                        "type": "text",
                        "text": prompt
                    },
                    {
                        "type": "image_url",
                        "image_url": {
                            "url": image_url
                        }
                    }
                ]
            }
        ]
    }

    try:
        logger.info(f"Отправка запроса на анализ изображения: {image_url[:50]}...")
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            data=json.dumps(payload),
            timeout=30  # Добавляем таймаут
        )
        response.raise_for_status()
        result = response.json()
        
        # Извлекаем текстовый ответ
        if result and "choices" in result and len(result["choices"]) > 0:
            text_response = result["choices"][0]["message"]["content"]
            # Включаем в возвращаемое значение как сырой ответ, так и извлеченный текст
            return {
                "raw_response": result,
                "text": text_response,
                "success": True
            }
        else:
            logger.warning("Неожиданный формат ответа от API")
            return {
                "raw_response": result,
                "text": None,
                "success": False
            }
            
    except requests.exceptions.RequestException as e:
        logger.error(f"Ошибка запроса: {str(e)}")
        return {
            "error": str(e),
            "text": None,
            "success": False
        }
    except Exception as e:
        logger.error(f"Непредвиденная ошибка: {str(e)}")
        return {
            "error": str(e),
            "text": None,
            "success": False
        }
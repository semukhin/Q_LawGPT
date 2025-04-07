import requests
import json

def analyze_image(api_key: str, image_url: str, prompt: str, 
                  site_url: str = None, site_name: str = None) -> str:
    """
    Анализирует изображение через OpenRouter API с использованием модели Qwen-VL
    
    Параметры:
    - api_key: Ваш API-ключ OpenRouter
    - image_url: Публичный URL изображения или base64 строка
    - prompt: Текст запроса к модели
    - site_url: Опционально - URL вашего сайта
    - site_name: Опционально - название приложения
    
    Возвращает:
    - Текстовый ответ модели
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
        response = requests.post(
            url="https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            data=json.dumps(payload)
        )
        response.raise_for_status()
        return response.json()
    except requests.exceptions.RequestException as e:
        print(f"Ошибка запроса: {str(e)}")
        return None

# Пример использования
if __name__ == "__main__":
    API_KEY = "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"
    IMAGE_URL = "https://upload.wikimedia.org/wikipedia/commons/thumb/d/dd/Gfp-wisconsin-madison-the-nature-boardwalk.jpg/2560px-Gfp-wisconsin-madison-the-nature-boardwalk.jpg"
    PROMPT = "Опиши подробно что изображено на картинке на русском языке"
    
    response = analyze_image(
        api_key=API_KEY,
        image_url=IMAGE_URL,
        prompt=PROMPT,
        site_url="https://your-lawgpt-app.com",
        site_name="LawGPT"
    )
    
    if response:
        print("Ответ модели:")
        print(response)
    else:
        print("Не удалось получить ответ")
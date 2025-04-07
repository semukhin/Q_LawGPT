import requests
import sys

def transcribe_audio(file_path):
    """
    Отправляет аудиофайл на сервер для транскрибации
    """
    url = "http://localhost:8001/transcribe"
    
    try:
        with open(file_path, 'rb') as audio_file:
            files = {'file': audio_file}
            response = requests.post(url, files=files)
            
            if response.status_code == 200:
                result = response.json()
                print("\nТранскрибация успешно завершена!")
                print("Текст:", result['text'])
            else:
                print(f"\nОшибка: {response.status_code}")
                print(response.text)
                
    except Exception as e:
        print(f"\nПроизошла ошибка: {str(e)}")

if __name__ == "__main__":
    if len(sys.argv) != 2:
        print("Использование: python test_whisper.py путь_к_аудиофайлу")
        sys.exit(1)
        
    file_path = sys.argv[1]
    transcribe_audio(file_path) 
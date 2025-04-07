# Q_LawGPT

Q_LawGPT - это юридический ассистент на базе искусственного интеллекта, разработанный для помощи в правовых вопросах.

## Возможности

- Аутентификация пользователей (регистрация, вход, восстановление пароля)
- Чат с AI-ассистентом
- Загрузка и анализ документов
- Голосовой ввод
- Генерация юридических документов

## Технологии

- Backend: FastAPI, SQLAlchemy, PostgreSQL
- Frontend: JavaScript, HTML, CSS
- AI: OpenAI GPT
- Дополнительно: Whisper API для распознавания речи

## Установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/YOUR_USERNAME/Q_LawGPT.git
cd Q_LawGPT
```

2. Создайте виртуальное окружение и установите зависимости:
```bash
python -m venv venv
source venv/bin/activate  # для Linux/Mac
venv\Scripts\activate  # для Windows
pip install -r requirements.txt
```

3. Создайте файл .env и настройте переменные окружения:
```env
SECRET_KEY=your-secret-key
POSTGRES_SERVER=localhost
POSTGRES_USER=your_user
POSTGRES_PASSWORD=your_password
POSTGRES_DB=your_db
```

4. Запустите приложение:
```bash
uvicorn app.main:app --reload
```

## Использование

После запуска приложение будет доступно по адресу http://localhost:8000

## Разработка

- Для запуска тестов: `pytest`
- Для проверки кода: `flake8`
- Для форматирования кода: `black .`

## Лицензия

MIT 
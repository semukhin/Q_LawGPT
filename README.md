# LawGPT

LawGPT - это юридический ассистент на базе искусственного интеллекта, разработанный для помощи в правовых вопросах с использованием технологий обработки естественного языка.

## Возможности

- Аутентификация пользователей (регистрация, вход, восстановление пароля)
- Чат с AI-ассистентом с использованием мультиагентной системы
- Загрузка и анализ юридических документов
- Голосовой ввод через Whisper API
- Генерация юридических документов
- Полнотекстовый поиск по законодательству через Elasticsearch
- Веб-интерфейс для взаимодействия с системой

## Компоненты системы

### Основное приложение
- **Backend**: FastAPI, SQLAlchemy, PostgreSQL
- **Мультиагентная система**: специализированные агенты для разных юридических задач
- **Middleware**: CSRF защита, аутентификация, логирование
- **WebSocket**: асинхронная связь с клиентом

### Whisper API сервис
- Отдельный микросервис для транскрибации аудио в текст
- Использует модель Whisper для распознавания русской речи

## Технологический стек

- **Backend**: FastAPI, SQLAlchemy, AsyncPG, PostgreSQL
- **Frontend**: JavaScript, HTML, CSS
- **AI**: Интеграция с языковыми моделями
- **Речь в текст**: Whisper API (трансформер для распознавания речи)
- **Хранение данных**: PostgreSQL (основное хранилище), ElasticSearch (для RAG)
- **Контейнеризация**: Docker, Docker Compose
- **Миграции базы данных**: Alembic

## Установка и запуск

### Локальная установка

1. Клонируйте репозиторий:
```bash
git clone https://github.com/semukhin/Q_LawGPT.git
cd Q_LawGPT
```

2. Создайте виртуальное окружение и установите зависимости:
```bash
python -m venv venv
source venv/bin/activate  # для Linux/Mac
venv\Scripts\activate  # для Windows
pip install -r requirements.txt
```

3. Создайте файл .env и настройте переменные окружения (пример в проекте)

4. Запустите миграции базы данных:
```bash
alembic upgrade head
```

5. Запустите основное приложение:
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

6. Процесс транскрибации Whisper API интегрирован в основное приложение.

### Запуск через Docker

Проект поддерживает Docker Compose для легкого развертывания:

```bash
docker-compose up -d
```

Это запустит:
- Основной сервис LawGPT на порту 8000
- БД PostgreSQL
- Elasticsearch

## Структура проекта

Q_LawGPT/
├── alembic/ # Миграции базы данных
│ ├── versions/ # Версии миграций
│ ├── env.py # Окружение для миграций
│ └── script.py.mako # Шаблон для миграций
├── app/ # Основной код приложения
│ ├── agents/ # Агенты для различных юридических задач
│ │ ├── analytics.py # Аналитический агент
│ │ ├── coordinator.py # Координатор агентов
│ │ ├── document_analysis.py # Анализ документов
│ │ ├── document_prep.py # Подготовка документов
│ │ ├── judicial.py # Судебный агент
│ │ └── legal_norms.py # Агент по правовым нормам
│ ├── api/ # API эндпоинты
│ │ ├── auth.py # Аутентификация
│ │ ├── chat.py # Чат API
│ │ ├── documents.py # API для работы с документами
│ │ ├── websockets.py # WebSockets API
│ │ └── whisper_api.py # API для Whisper
│ ├── core/ # Ядро приложения
│ │ ├── config.py # Конфигурация
│ │ ├── database.py # Настройки базы данных
│ │ └── security.py # Безопасность и аутентификация
│ ├── db/ # Модели базы данных
│ ├── rag/ # Retrieval-Augmented Generation модули
│ │ ├── elastic.py # Интеграция с Elasticsearch
│ │ ├── retrieval.py # Поиск и извлечение данных
│ │ └── indexing.py # Индексирование данных
│ ├── schemas/ # Pydantic схемы
│ ├── scripts/ # Вспомогательные скрипты
│ │ └── index_rag_data.py # Индексирование данных для RAG
│ ├── services/ # Сервисы
│ │ ├── ai_service.py # Сервис AI
│ │ ├── chat.py # Сервис чата
│ │ ├── document.py # Сервис для работы с документами
│ │ ├── elasticsearch_service.py # Сервис для ElasticSearch
│ │ ├── image_analysis.py # Анализ изображений
│ │ ├── voice.py # Сервис для голосового ввода
│ │ └── web_search.py # Сервис для поиска в интернете
│ ├── utils/ # Утилиты
│ ├── init.py # Инициализация пакета
│ └── main.py # Точка входа FastAPI приложения
├── static/ # Статические файлы
├── .gitignore # Список исключений для git
├── alembic.ini # Конфигурация Alembic
├── docker-compose.yml # Конфигурация Docker Compose
├── Dockerfile.whisper # Dockerfile для Whisper API сервиса
└── requirements.txt # Зависимости Python


## Разработка

- Для запуска тестов: `pytest`
- Для проверки кода: `flake8`
- Для форматирования кода: `black .`
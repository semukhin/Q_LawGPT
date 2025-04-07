from elasticsearch import Elasticsearch
import logging
import psycopg2
from psycopg2.extras import DictCursor
from datetime import datetime
import threading
import queue
import concurrent.futures
import os
from dotenv import load_dotenv

# Загружаем переменные окружения
load_dotenv()

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s: %(message)s'
)

# Конфигурация Elasticsearch
ES_HOST = os.getenv("ELASTICSEARCH_URL", "http://localhost:9200")
ES_USER = os.getenv("ELASTICSEARCH_USER", "elastic")  # Имя пользователя по умолчанию
ES_PASS = os.getenv("ELASTICSEARCH_PASSWORD", "GIkb8BKzkXK7i2blnG2O")  # Пароль по умолчанию

# Конфигурация базы данных RAG
DB_CONFIG = {
    "host": os.getenv("RAG_POSTGRES_SERVER", "82.97.242.92"),
    "database": os.getenv("RAG_POSTGRES_DB", "ruslaw_db"),
    "user": os.getenv("RAG_POSTGRES_USER", "gen_user"),
    "password": os.getenv("RAG_POSTGRES_PASSWORD", "P?!ri#ag5%G1Si"),
    "port": os.getenv("RAG_POSTGRES_PORT", "5432")
}

# Определение таблиц и индексов для индексации
ES_INDICES = {
    "ruslawod_chunks": "law_chunks_index",
    "court_decisions": "court_decisions_index",
    "court_reviews": "court_reviews_index",
    "legal_articles": "legal_articles_index"
}

# Глобальный словарь для хранения статуса индексации
indexing_status = {
    "is_running": False,
    "total_tables": 0,
    "completed_tables": 0,
    "current_progress": {},
    "errors": []
}

# Блокировка для безопасного обновления статуса
status_lock = threading.Lock()

def update_indexing_status(table_name=None, progress=None, error=None):
    """Обновляет статус индексации"""
    with status_lock:
        if error:
            indexing_status["errors"].append({"table": table_name, "error": str(error)})
        if progress is not None:
            indexing_status["current_progress"][table_name] = progress
        if table_name and progress == 100:
            indexing_status["completed_tables"] += 1

def get_indexing_status():
    """Возвращает текущий статус индексации"""
    with status_lock:
        return dict(indexing_status)

# Определение маппингов для индексов
MAPPINGS = {
    "law_chunks_index": {
        "mappings": {
            "properties": {
                "id": {"type": "integer"},
                "doc_id": {"type": "keyword"},
                "chunk_id": {"type": "integer"},
                "text_chunk": {"type": "text", "analyzer": "russian"},
                "indexed_at": {"type": "date"}
            }
        }
    },
    "court_decisions_index": {
        "mappings": {
            "properties": {
                "id": {"type": "integer"},
                "doc_id": {"type": "keyword"},
                "chunk_id": {"type": "integer"},
                "case_number": {"type": "keyword"},
                "court_name": {"type": "text", "analyzer": "russian"},
                "vidpr": {"type": "keyword"},
                "etapd": {"type": "keyword"},
                "result": {"type": "text", "analyzer": "russian"},
                "date": {"type": "date"},
                "vid_dokumenta": {"type": "keyword"},
                "instance": {"type": "keyword"},
                "region": {"type": "keyword"},
                "judges": {"type": "text", "analyzer": "russian"},
                "claimant": {"type": "text", "analyzer": "russian"},
                "defendant": {"type": "text", "analyzer": "russian"},
                "subject": {"type": "text", "analyzer": "russian"},
                "arguments": {"type": "text", "analyzer": "russian"},
                "conclusion": {"type": "text", "analyzer": "russian"},
                "full_text": {"type": "text", "analyzer": "russian"},
                "laws": {"type": "text", "analyzer": "russian"},
                "amount": {"type": "float"},
                "indexed_at": {"type": "date"}
            }
        }
    },
    "court_reviews_index": {
        "mappings": {
            "properties": {
                "id": {"type": "integer"},
                "doc_id": {"type": "keyword"},
                "chunk_id": {"type": "integer"},
                "title": {"type": "text", "analyzer": "russian"},
                "subject": {"type": "text", "analyzer": "russian"},
                "conclusion": {"type": "text", "analyzer": "russian"},
                "referenced_cases": {"type": "object"},
                "full_text": {"type": "text", "analyzer": "russian"},
                "created_at": {"type": "date"},
                "updated_at": {"type": "date"},
                "indexed_at": {"type": "date"}
            }
        }
    },
    "legal_articles_index": {
        "mappings": {
            "properties": {
                "id": {"type": "integer"},
                "doc_id": {"type": "keyword"},
                "chunk_id": {"type": "integer"},
                "title": {"type": "text", "analyzer": "russian"},
                "author": {"type": "text", "analyzer": "russian"},
                "publication_date": {"type": "date"},
                "source": {"type": "keyword"},
                "subject": {"type": "text", "analyzer": "russian"},
                "summary": {"type": "text", "analyzer": "russian"},
                "legal_norms": {"type": "object"},
                "court_cases": {"type": "object"},
                "full_text": {"type": "text", "analyzer": "russian"},
                "extra_data": {"type": "object"},
                "created_at": {"type": "date"},
                "indexed_at": {"type": "date"}
            }
        }
    }
}

def get_es_client():
    """Создает и возвращает клиент Elasticsearch"""
    try:
        # Проверяем, нужно ли использовать аутентификацию
        if ES_USER and ES_PASS and ES_USER.strip() and ES_PASS.strip():
            logging.info(f"Подключение к Elasticsearch с аутентификацией: {ES_HOST}")
            es = Elasticsearch(
                [ES_HOST],
                basic_auth=(ES_USER, ES_PASS),
                retry_on_timeout=True,
                max_retries=3
            )
        else:
            logging.info(f"Подключение к Elasticsearch без аутентификации: {ES_HOST}")
            es = Elasticsearch(
                [ES_HOST],
                retry_on_timeout=True,
                max_retries=3
            )
        
        # Проверяем подключение
        if es.ping():
            logging.info("Успешное подключение к Elasticsearch")
            return es
        else:
            logging.error("Не удалось подключиться к Elasticsearch")
            raise ConnectionError("Не удалось подключиться к Elasticsearch")
    except Exception as e:
        logging.error(f"Ошибка подключения к Elasticsearch: {e}")
        raise

def create_index(es, index_name, mapping):
    """Создает индекс с указанным маппингом"""
    try:
        if not es.indices.exists(index=index_name):
            es.indices.create(index=index_name, body=mapping)
            logging.info(f"Создан индекс {index_name}")
        else:
            logging.info(f"Индекс {index_name} уже существует")
    except Exception as e:
        logging.error(f"Ошибка при создании индекса {index_name}: {e}")
        raise

def get_db_connection():
    """Создает подключение к PostgreSQL"""
    try:
        conn = psycopg2.connect(**DB_CONFIG)
        return conn
    except Exception as e:
        logging.error(f"Ошибка подключения к PostgreSQL: {e}")
        raise

def index_table_data_batch(es, conn, table_name, index_name, batch_size=1000):
    """Индексирует данные из таблицы PostgreSQL в Elasticsearch батчами"""
    try:
        cursor = conn.cursor(cursor_factory=DictCursor)
        
        # Получаем общее количество записей
        cursor.execute(f"SELECT COUNT(*) FROM {table_name}")
        total_rows = cursor.fetchone()[0]
        
        if total_rows == 0:
            logging.info(f"Таблица {table_name} пуста")
            update_indexing_status(table_name, 100)
            return
            
        logging.info(f"Начало индексации {total_rows} записей из таблицы {table_name}")
        
        # Обрабатываем данные батчами
        offset = 0
        while offset < total_rows:
            cursor.execute(f"SELECT * FROM {table_name} LIMIT {batch_size} OFFSET {offset}")
            rows = cursor.fetchall()
            
            if not rows:
                break
                
            # Подготавливаем батч для bulk индексации
            bulk_data = []
            for row in rows:
                doc = dict(row)
                doc['indexed_at'] = datetime.now().isoformat()
                doc_id = str(doc.get('id'))
                
                # Добавляем операцию индексации в батч
                bulk_data.extend([
                    {"index": {"_index": index_name, "_id": doc_id}},
                    doc
                ])
            
            # Выполняем bulk индексацию
            if bulk_data:
                es.bulk(operations=bulk_data)
            
            offset += batch_size
            progress = min(100, int(offset * 100 / total_rows))
            update_indexing_status(table_name, progress)
            logging.info(f"Проиндексировано {min(offset, total_rows)}/{total_rows} записей из таблицы {table_name}")
        
        update_indexing_status(table_name, 100)
        logging.info(f"Завершена индексация таблицы {table_name}")
        
    except Exception as e:
        logging.error(f"Ошибка при индексации таблицы {table_name}: {e}")
        update_indexing_status(table_name=table_name, error=e)
        raise
    finally:
        cursor.close()

def index_table_async(table_name, index_name):
    """Асинхронная индексация одной таблицы"""
    try:
        es = get_es_client()
        conn = get_db_connection()
        
        try:
            # Создаем индекс если не существует
            if not es.indices.exists(index=index_name):
                es.indices.create(index=index_name, body=MAPPINGS[index_name])
                logging.info(f"Создан индекс {index_name}")
            
            # Индексируем данные
            index_table_data_batch(es, conn, table_name, index_name)
            
        finally:
            conn.close()
            
    except Exception as e:
        logging.error(f"Ошибка при индексации таблицы {table_name}: {e}")

def init_elasticsearch_async():
    """Инициализирует индексы Elasticsearch и запускает асинхронную индексацию"""
    try:
        # Проверяем подключение к Elasticsearch
        es = get_es_client()
        if not es.ping():
            raise ConnectionError("Не удалось подключиться к Elasticsearch")
            
        # Проверяем подключение к PostgreSQL
        conn = get_db_connection()
        conn.close()
        
        # Инициализируем статус
        with status_lock:
            indexing_status["is_running"] = True
            indexing_status["total_tables"] = len(ES_INDICES)
            indexing_status["completed_tables"] = 0
            indexing_status["current_progress"] = {}
            indexing_status["errors"] = []
        
        # Создаем и запускаем поток для индексации
        def indexing_thread():
            try:
                with concurrent.futures.ThreadPoolExecutor(max_workers=4) as executor:
                    futures = []
                    for table_name, index_name in ES_INDICES.items():
                        future = executor.submit(index_table_async, table_name, index_name)
                        futures.append(future)
                    
                    # Ждем завершения всех задач
                    concurrent.futures.wait(futures, return_when=concurrent.futures.FIRST_EXCEPTION)
                    logging.info("Индексация всех таблиц завершена")
            finally:
                with status_lock:
                    indexing_status["is_running"] = False
        
        # Запускаем индексацию в отдельном потоке
        thread = threading.Thread(target=indexing_thread)
        thread.daemon = True
        thread.start()
        
        logging.info("Запущена асинхронная индексация всех таблиц")
        return True
        
    except Exception as e:
        logging.error(f"Ошибка при инициализации Elasticsearch: {e}")
        return False

if __name__ == "__main__":
    init_elasticsearch_async()
    # Держим главный поток живым для демонстрации
    import time
    time.sleep(3600) 
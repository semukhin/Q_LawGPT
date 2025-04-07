#!/usr/bin/python
import psycopg2

def test_main_db_connection():
    try:
        conn = psycopg2.connect(
            host="147.45.232.224",
            database="default_db",
            user="gen_user",
            password="Grisha1977!",
            port="5432"
        )
        print("✅ Успешное подключение к основной базе данных")
        conn.close()
    except Exception as e:
        print(f"❌ Ошибка подключения к основной базе данных: {str(e)}")

def test_rag_db_connection():
    try:
        conn = psycopg2.connect(
            host="82.97.242.92",
            database="ruslaw_db",
            user="gen_user",
            password="P?!ri#ag5%G1Si",
            port="5432"
        )
        print("✅ Успешное подключение к RAG базе данных")
        conn.close()
    except Exception as e:
        print(f"❌ Ошибка подключения к RAG базе данных: {str(e)}")

if __name__ == "__main__":
    print("Тестирование подключений к базам данных...")
    test_main_db_connection()
    test_rag_db_connection() 
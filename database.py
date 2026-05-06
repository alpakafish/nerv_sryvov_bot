import asyncpg
import os
from datetime import datetime
import pytz
from config import TIMEZONE
from encryption import encrypt_message, decrypt_message

DATABASE_URL = os.getenv("DATABASE_URL")


async def get_db_connection():
    """Возвращает соединение с базой данных"""
    return await asyncpg.connect(DATABASE_URL)


def get_server_date():
    """Возвращает текущую дату в серверной временной зоне"""
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    return now.strftime('%Y-%m-%d')


async def init_db():
    """Создает таблицы при запуске бота, если они не существуют"""
    conn = await get_db_connection()
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id BIGINT PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            registered_at TIMESTAMP
        )
    ''')
    await conn.execute('''
        CREATE TABLE IF NOT EXISTS stresses (
            id SERIAL PRIMARY KEY,
            user_id BIGINT,
            message_text TEXT,
            created_at TIMESTAMP,
            server_date TEXT,
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')
    await conn.close()


async def register_user(user_id, username, first_name, last_name):
    """Регистрирует пользователя, если его еще нет"""
    conn = await get_db_connection()
    await conn.execute('''
        INSERT INTO users (user_id, username, first_name, last_name, registered_at)
        VALUES ($1, $2, $3, $4, $5)
        ON CONFLICT (user_id) DO NOTHING
    ''', user_id, username, first_name, last_name, datetime.now())
    await conn.close()


async def save_stress_message(user_id, message_text):
    """Сохраняет сообщение о срыве В ЗАШИФРОВАННОМ виде"""
    conn = await get_db_connection()
    server_date = get_server_date()

    # 🔐 Шифруем текст перед сохранением
    encrypted_text = encrypt_message(message_text)

    await conn.execute('''
        INSERT INTO stresses (user_id, message_text, created_at, server_date)
        VALUES ($1, $2, $3, $4)
    ''', user_id, encrypted_text, datetime.now(), server_date)
    await conn.close()


async def get_today_stresses(user_id):
    """Получает и РАСШИФРОВЫВАЕТ срывы пользователя за сегодня"""
    conn = await get_db_connection()
    server_date = get_server_date()
    rows = await conn.fetch('''
        SELECT message_text, created_at 
        FROM stresses 
        WHERE user_id = $1 AND server_date = $2
        ORDER BY created_at
    ''', user_id, server_date)
    await conn.close()

    # 🔓 Расшифровываем каждое сообщение
    result = []
    for row in rows:
        decrypted_text = decrypt_message(row['message_text'])
        result.append({
            'message_text': decrypted_text,
            'created_at': row['created_at']
        })
    return result


async def get_next_today_number(user_id):
    """Получает следующий порядковый номер для сообщения за сегодня"""
    stresses = await get_today_stresses(user_id)
    return len(stresses) + 1


async def get_month_stresses(user_id):
    """Получает и РАСШИФРОВЫВАЕТ срывы пользователя за месяц"""
    conn = await get_db_connection()
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    year = now.year
    month = now.month
    rows = await conn.fetch('''
        SELECT message_text, created_at 
        FROM stresses 
        WHERE user_id = $1 
        AND EXTRACT(YEAR FROM created_at) = $2 
        AND EXTRACT(MONTH FROM created_at) = $3
        ORDER BY created_at
    ''', user_id, year, month)
    await conn.close()

    # 🔓 Расшифровываем каждое сообщение
    result = []
    for row in rows:
        decrypted_text = decrypt_message(row['message_text'])
        result.append({
            'message_text': decrypted_text,
            'created_at': row['created_at']
        })
    return result


async def get_total_stresses(user_id):
    """Получает общее количество срывов пользователя за все время"""
    conn = await get_db_connection()
    count = await conn.fetchval('''
        SELECT COUNT(*) FROM stresses WHERE user_id = $1
    ''', user_id)
    await conn.close()
    return count or 0


async def get_month_statistics(user_id):
    """Получает статистику по дням за текущий месяц"""
    conn = await get_db_connection()
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    year = now.year
    month = now.month
    rows = await conn.fetch('''
        SELECT EXTRACT(DAY FROM created_at) as day, COUNT(*) as count
        FROM stresses 
        WHERE user_id = $1 
        AND EXTRACT(YEAR FROM created_at) = $2 
        AND EXTRACT(MONTH FROM created_at) = $3
        GROUP BY EXTRACT(DAY FROM created_at)
    ''', user_id, year, month)
    await conn.close()
    stats = {int(row['day']): row['count'] for row in rows}
    return stats
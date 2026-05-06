import sqlite3
from datetime import datetime
from config import TIMEZONE
import pytz


def get_db_connection():
    """Создает подключение к базе данных"""
    conn = sqlite3.connect('stress_bot.db')
    conn.row_factory = sqlite3.Row  # Чтобы получать данные как словари
    return conn


def init_db():
    """Создает таблицы при первом запуске"""
    conn = get_db_connection()
    cursor = conn.cursor()

    # Таблица пользователей
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS users (
            user_id INTEGER PRIMARY KEY,
            username TEXT,
            first_name TEXT,
            last_name TEXT,
            registered_at TIMESTAMP
        )
    ''')

    # Таблица сообщений (срывов)
    cursor.execute('''
        CREATE TABLE IF NOT EXISTS stresses (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            user_id INTEGER,
            message_text TEXT,
            created_at TIMESTAMP,
            server_date TEXT,  -- Дата в формате ГГГГ-ММ-ДД для серверных суток
            FOREIGN KEY (user_id) REFERENCES users (user_id)
        )
    ''')

    conn.commit()
    conn.close()


def get_server_date():
    """Возвращает текущую дату в серверной временной зоне"""
    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    return now.strftime('%Y-%m-%d')


def register_user(user_id, username, first_name, last_name):
    """Регистрирует пользователя, если его еще нет"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        INSERT OR IGNORE INTO users (user_id, username, first_name, last_name, registered_at)
        VALUES (?, ?, ?, ?, ?)
    ''', (user_id, username, first_name, last_name, datetime.now()))

    conn.commit()
    conn.close()


def save_stress_message(user_id, message_text):
    """Сохраняет сообщение о срыве в базу данных"""
    conn = get_db_connection()
    cursor = conn.cursor()

    server_date = get_server_date()

    cursor.execute('''
        INSERT INTO stresses (user_id, message_text, created_at, server_date)
        VALUES (?, ?, ?, ?)
    ''', (user_id, message_text, datetime.now(), server_date))

    conn.commit()
    conn.close()


def get_today_stresses(user_id):
    """Получает все срывы пользователя за текущие серверные сутки"""
    conn = get_db_connection()
    cursor = conn.cursor()

    server_date = get_server_date()

    cursor.execute('''
        SELECT message_text, created_at 
        FROM stresses 
        WHERE user_id = ? AND server_date = ?
        ORDER BY created_at
    ''', (user_id, server_date))

    stresses = cursor.fetchall()
    conn.close()
    return stresses


def get_month_stresses(user_id):
    """Получает все срывы пользователя за текущий календарный месяц"""
    conn = get_db_connection()
    cursor = conn.cursor()

    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    year = now.year
    month = now.month

    cursor.execute('''
        SELECT message_text, created_at 
        FROM stresses 
        WHERE user_id = ? 
        AND strftime('%Y', created_at) = ? 
        AND strftime('%m', created_at) = ?
        ORDER BY created_at
    ''', (user_id, str(year), f"{month:02d}"))

    stresses = cursor.fetchall()
    conn.close()
    return stresses


def get_total_stresses(user_id):
    """Получает общее количество срывов пользователя за все время"""
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute('''
        SELECT COUNT(*) as count 
        FROM stresses 
        WHERE user_id = ?
    ''', (user_id,))

    result = cursor.fetchone()
    conn.close()
    return result['count'] if result else 0


def get_month_statistics(user_id):
    """Получает статистику по дням за текущий месяц"""
    conn = get_db_connection()
    cursor = conn.cursor()

    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    year = now.year
    month = now.month

    # Получаем количество сообщений по дням
    cursor.execute('''
        SELECT strftime('%d', created_at) as day, COUNT(*) as count
        FROM stresses 
        WHERE user_id = ? 
        AND strftime('%Y', created_at) = ? 
        AND strftime('%m', created_at) = ?
        GROUP BY strftime('%d', created_at)
    ''', (user_id, str(year), f"{month:02d}"))

    results = cursor.fetchall()
    conn.close()

    # Преобразуем в словарь {день: количество}
    stats = {int(row['day']): row['count'] for row in results}
    return stats


def get_next_today_number(user_id):
    """Получает следующий порядковый номер для сообщения за сегодня"""
    stresses = get_today_stresses(user_id)
    return len(stresses) + 1
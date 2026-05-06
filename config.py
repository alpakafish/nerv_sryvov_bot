import os
from dotenv import load_dotenv

# Загружаем переменные из файла .env
load_dotenv()

# Токен бота из переменных окружения
BOT_TOKEN = os.getenv("BOT_TOKEN")

# Временная зона сервера (для Москвы - UTC+3, можно изменить под свой часовой пояс)
# Для точного определения серверного времени используем UTC
# Если нужно московское время, замени на 'Europe/Moscow'
TIMEZONE = 'UTC'
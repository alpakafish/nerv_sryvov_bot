import asyncio
from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import ReplyKeyboardMarkup, KeyboardButton, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.fsm.context import FSMContext
from aiogram.fsm.state import State, StatesGroup
from aiogram.fsm.storage.memory import MemoryStorage

from config import BOT_TOKEN
from database import (
    init_db, register_user, save_stress_message,
    get_today_stresses, get_month_stresses, get_total_stresses,
    get_month_statistics, get_next_today_number
)
from datetime import datetime
import calendar
import pytz
from config import TIMEZONE

# Создаем бота и диспетчер
bot = Bot(token=BOT_TOKEN)
storage = MemoryStorage()
dp = Dispatcher(storage=storage)


# Определяем состояния для FSM
class StressState(StatesGroup):
    waiting_for_reason = State()  # Ждем текст причины срыва


# Создаем клавиатуру меню
def get_main_keyboard():
    buttons = [
        [KeyboardButton(text="😫 Причина нервного срыва")],
        [KeyboardButton(text="📆 Срывы за сегодня")],
        [KeyboardButton(text="📅 Срывы за месяц")],
        [KeyboardButton(text="📊 Всего срывов")],
        [KeyboardButton(text="📈 Статистика месяца")]
    ]
    keyboard = ReplyKeyboardMarkup(
        keyboard=buttons,
        resize_keyboard=True,
        one_time_keyboard=False
    )
    return keyboard


# Обработчик команды /start
@dp.message(Command("start"))
async def cmd_start(message: types.Message):
    # Регистрируем пользователя
    user = message.from_user
    register_user(
        user.id,
        user.username,
        user.first_name,
        user.last_name
    )

    await message.answer(
        f"Привет, {user.first_name}! 👋\n\n"
        f"Я бот для отслеживания нервных срывов.\n"
        f"Выбери действие в меню:",
        reply_markup=get_main_keyboard()
    )


# Обработчик кнопки "Причина нервного срыва"
@dp.message(lambda message: message.text == "😫 Причина нервного срыва")
async def add_stress(message: types.Message, state: FSMContext):
    # Получаем следующий номер за сегодня
    next_number = get_next_today_number(message.from_user.id)
    await state.set_state(StressState.waiting_for_reason)
    await message.answer(
        f"📝 Напиши, что вывело тебя из себя.\n"
        f"Это будет твой срыв #{next_number} за сегодня.",
        reply_markup=types.ReplyKeyboardRemove()  # Убираем меню на время ввода
    )


# Обработчик текста причины срыва
@dp.message(StressState.waiting_for_reason)
async def process_stress_reason(message: types.Message, state: FSMContext):
    if not message.text or len(message.text.strip()) == 0:
        await message.answer("Пожалуйста, напиши текст причины.")
        return

    reason_text = message.text.strip()
    user_id = message.from_user.id

    # Сохраняем в базу данных
    save_stress_message(user_id, reason_text)

    # Получаем номер сообщения
    number = get_next_today_number(user_id)

    await state.clear()  # Очищаем состояние
    await message.answer(
        f"✅ Срыв #{number - 1} за сегодня сохранен!\n\n"
        f"Твой текст: {reason_text}\n\n"
        f"Вернуться в меню: /start",
        reply_markup=get_main_keyboard()
    )


# Обработчик кнопки "Срывы за сегодня"
@dp.message(lambda message: message.text == "📆 Срывы за сегодня")
async def show_today_stresses(message: types.Message):
    stresses = get_today_stresses(message.from_user.id)

    if not stresses:
        await message.answer(
            "🎉 Вау, спокойный день! Сегодня без срывов.",
            reply_markup=get_main_keyboard()
        )
        return

    # Формируем ответ
    response = "📆 *Твои срывы за сегодня:*\n\n"
    for i, stress in enumerate(stresses, 1):
        created_at = datetime.fromisoformat(str(stress['created_at']))
        time_str = created_at.strftime("%H:%M")
        response += f"{i}. {stress['message_text']} ({time_str})\n"

    await message.answer(response, reply_markup=get_main_keyboard(), parse_mode="Markdown")


# Обработчик кнопки "Срывы за месяц"
@dp.message(lambda message: message.text == "📅 Срывы за месяц")
async def show_month_stresses(message: types.Message):
    stresses = get_month_stresses(message.from_user.id)

    if not stresses:
        tz = pytz.timezone(TIMEZONE)
        now = datetime.now(tz)
        month_name = now.strftime("%B")
        await message.answer(
            f"📅 За {month_name} у тебя не было срывов. Отлично!",
            reply_markup=get_main_keyboard()
        )
        return

    # Формируем ответ (показываем последние 20, чтобы не перегружать)
    response = f"📅 *Твои срывы за {datetime.now(pytz.timezone(TIMEZONE)).strftime('%B %Y')}:*\n\n"
    for i, stress in enumerate(stresses[-20:], 1):
        created_at = datetime.fromisoformat(str(stress['created_at']))
        date_str = created_at.strftime("%d.%m %H:%M")
        response += f"{i}. {stress['message_text']} ({date_str})\n"

    if len(stresses) > 20:
        response += f"\n*Всего срывов за месяц: {len(stresses)}*"

    await message.answer(response, reply_markup=get_main_keyboard(), parse_mode="Markdown")


# Обработчик кнопки "Всего срывов"
@dp.message(lambda message: message.text == "📊 Всего срывов")
async def show_total_stresses(message: types.Message):
    total = get_total_stresses(message.from_user.id)

    if total == 0:
        await message.answer(
            "🌟 Ты еще ни разу не сообщал о срывах. Продолжай в том же духе!",
            reply_markup=get_main_keyboard()
        )
    elif total == 1:
        await message.answer(
            f"📊 За все время у тебя был {total} срыв.",
            reply_markup=get_main_keyboard()
        )
    elif 2 <= total <= 4:
        await message.answer(
            f"📊 За все время у тебя было {total} срыва.",
            reply_markup=get_main_keyboard()
        )
    else:
        await message.answer(
            f"📊 За все время у тебя было {total} срывов.",
            reply_markup=get_main_keyboard()
        )


# Обработчик кнопки "Статистика месяца"
@dp.message(lambda message: message.text == "📈 Статистика месяца")
async def show_month_stats(message: types.Message):
    stats = get_month_statistics(message.from_user.id)

    tz = pytz.timezone(TIMEZONE)
    now = datetime.now(tz)
    year = now.year
    month = now.month

    # Получаем количество дней в месяце
    days_in_month = calendar.monthrange(year, month)[1]

    # Русские названия месяцев
    months_ru = {
        1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
        5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
        9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь"
    }
    month_name_ru = months_ru[month]

    # Формируем статистику в простом текстовом формате
    response = f"📈 *Статистика за {month_name_ru} {year}:*\n\n"

    # Собираем строки с днями, где есть срывы
    days_with_stresses = []
    for day in range(1, days_in_month + 1):
        count = stats.get(day, 0)
        if count > 0:
            # Визуализация полосками (максимум 15 полосок)
            bars = "█" * min(count, 15)
            days_with_stresses.append(f"• {day:2d}.{month:02d} — {count} {bars}")

    if days_with_stresses:
        response += "\n".join(days_with_stresses)
    else:
        response += "✨ *В этом месяце не было ни одного срыва!* ✨"

    # Добавляем итог
    total_month = sum(stats.values())
    if total_month > 0:
        response += f"\n\n*📊 Всего за месяц: {total_month}*"

    await message.answer(response, reply_markup=get_main_keyboard(), parse_mode="Markdown")


# Обработчик непонятных сообщений
@dp.message()
async def handle_unknown(message: types.Message):
    await message.answer(
        "Пожалуйста, используй кнопки меню. Если меню пропало, нажми /start",
        reply_markup=get_main_keyboard()
    )


# Запуск бота
async def main():
    # Инициализируем базу данных
    init_db()
    print("✅ Бот запущен и готов к работе!")
    print(f"📁 База данных: stress_bot.db")
    print(f"🕐 Временная зона сервера: {TIMEZONE}")

    # Запускаем бота
    await dp.start_polling(bot)

# Добавь эти строки в bot.py для работы на Render
from flask import Flask
import threading
import os

flask_app = Flask(__name__)

@flask_app.route('/')
def hello():
    return "Bot is running!"

@flask_app.route('/health')
def health():
    return "OK"

def run_flask():
    port = int(os.environ.get("PORT", 5000))
    flask_app.run(host="0.0.0.0", port=port)

# Запускаем Flask в отдельном потоке
threading.Thread(target=run_flask).start()


if __name__ == "__main__":
    asyncio.run(main())
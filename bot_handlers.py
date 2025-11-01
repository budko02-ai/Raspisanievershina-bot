# bot_handlers.py
import os
import asyncio
import logging
from aiogram import Bot, Dispatcher, types
from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo
from aiogram.utils import exceptions

logger = logging.getLogger("vershina.bot")

BOT_TOKEN = os.getenv("7858173225:AAG8_RBaAV1t819srHp6U2R23EscHXpQOtg")
ADMIN_ID = int(os.getenv("@Teachermath_1", "0"))

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(bot)

# We will start dispatcher in background from main.py by calling start_bot(sheets)
# Simple handlers:

@dp.message_handler(commands=["start"])
async def cmd_start(message: types.Message):
    user_id = message.from_user.id
    # If admin -> show admin open-panel button
    if user_id == ADMIN_ID:
        keyboard = InlineKeyboardMarkup().add(
            InlineKeyboardButton("Открыть панель администратора", web_app=WebAppInfo(url=f"{get_base_url()}/"))
        )
        await message.answer("Привет, админ! Открой панель:", reply_markup=keyboard)
    else:
        keyboard = InlineKeyboardMarkup().add(
            InlineKeyboardButton("Моя панель (репетитор)", web_app=WebAppInfo(url=f"{get_base_url()}/"))
        )
        await message.answer("Привет! Открой свою панель:", reply_markup=keyboard)

@dp.message_handler(commands=["help"])
async def cmd_help(message: types.Message):
    await message.answer("Бот WebApp для центра Вершина знаний. Нажми кнопку 'Моя панель' чтобы открыть интерфейс.")

@dp.message_handler(commands=["pay"])
async def cmd_pay(message: types.Message):
    # admin command: /pay <lesson_id>
    if message.from_user.id != ADMIN_ID:
        await message.reply("Только админ.")
        return
    parts = message.text.strip().split()
    if len(parts) < 2:
        await message.reply("Использование: /pay <lesson_id>")
        return
    lesson_id = parts[1]
    from sheets_api import SheetsAPI, get_global_sheets
    sheets = get_global_sheets()
    ok = sheets.mark_lesson_paid(int(lesson_id))
    if ok:
        await message.reply(f"Урок {lesson_id} отмечен как оплаченный.")
    else:
        await message.reply("Не нашёл урок с таким ID.")

async def start_bot(sheets):
    """
    Called from main.py. We pass sheets instance so bot can use it if needed.
    """
    # set global sheets in module to be importable by handlers
    from sheets_api import set_global_sheets
    set_global_sheets(sheets)

    # Start polling
    loop = asyncio.get_event_loop()
    # run polling in background task so uvicorn can continue
    asyncio.create_task(dp.start_polling())

def get_base_url():
    # Base URL for webapp; prefer RENDER_EXTERNAL_URL if provided (Render sets it)
    base = os.getenv("RENDER_EXTERNAL_URL") or os.getenv("WEBAPP_BASE_URL") or f"https://{os.getenv('RENDER_SERVICE_NAME','localhost')}.onrender.com"
    # if running locally, use localhost:8000
    if base.startswith("http"):
        return base
    return f"http://localhost:8000"

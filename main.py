# main.py
import os
import base64
import tempfile
import logging
import asyncio
from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import HTMLResponse, FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
import uvicorn
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from bot_handlers import start_bot
from sheets_api import SheetsAPI, ensure_sheets_exist

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("vershina")

# --- Read env ---
BOT_TOKEN = os.getenv("7858173225:AAG8_RBaAV1t819srHp6U2R23EscHXpQOtg")
ADMIN_ID = int(os.getenv("@Teachermath_1", "0"))
SPREADSHEET_ID = os.getenv("1fjYlP6aY-he7SLrid-l8zsGCjyKMWYM7eRYz4iE-etc")
CRED_B64 = os.getenv("GOOGLE_CREDENTIALS_JSON_BASE64")
REMINDER_MIN = int(os.getenv("REMINDER_LEAD_MINUTES", "60"))

if not all([BOT_TOKEN, ADMIN_ID, SPREADSHEET_ID, CRED_B64]):
    logger.error("Missing environment variables. Set BOT_TOKEN, ADMIN_TELEGRAM_ID, SPREADSHEET_ID, GOOGLE_CREDENTIALS_JSON_BASE64")
    raise SystemExit("Missing environment variables")

# decode credentials to temp file
tmpdir = tempfile.gettempdir()
cred_path = os.path.join(tmpdir, "service_account_vershina.json")
with open(cred_path, "wb") as f:
    f.write(base64.b64decode(CRED_B64))
logger.info("Decoded Google credentials to %s", cred_path)

# Initialize SheetsAPI
sheets = SheetsAPI(cred_path, SPREADSHEET_ID)
ensure_sheets_exist(sheets)

# FastAPI app
app = FastAPI()
app.mount("/static", StaticFiles(directory="webapp/static"), name="static")

# Serve main WebApp page
@app.get("/", response_class=HTMLResponse)
async def root():
    return FileResponse("webapp/index.html")

# API endpoint used by WebApp to add slot (tutor)
@app.post("/api/add_slot")
async def add_slot(request: Request):
    data = await request.json()
    # Expecting: { "tg_user_id": 12345, "date": "YYYY-MM-DD", "time": "HH:MM", "note": "..." }
    tg = data.get("tg_user_id")
    date = data.get("date")
    time = data.get("time")
    note = data.get("note", "")
    if not all([tg, date, time]):
        raise HTTPException(status_code=400, detail="tg_user_id, date and time required")
    sheets.append_slot(int(tg), date, time, note)
    return JSONResponse({"status": "ok"})

# API endpoint for admin to add lesson
@app.post("/api/add_lesson")
async def api_add_lesson(request: Request):
    data = await request.json()
    # Expecting: { "admin_id": 123, "tutor_id": 456, "student": "Имя", "date": "YYYY-MM-DD", "time": "HH:MM", "amount": 1000 }
    admin_id = int(data.get("admin_id", 0))
    if admin_id != ADMIN_ID:
        raise HTTPException(status_code=403, detail="Forbidden")
    tutor = int(data.get("tutor_id"))
    student = data.get("student")
    date = data.get("date")
    time = data.get("time")
    amount = float(data.get("amount", 0))
    lesson_id = sheets.append_lesson(date, time, tutor, student, amount)
    return JSONResponse({"status": "ok", "lesson_id": lesson_id})

# API to fetch tutor's slots (used by WebApp)
@app.get("/api/my_slots/{tg_user_id}")
async def api_my_slots(tg_user_id: int):
    slots = sheets.get_slots_for_tutor(tg_user_id)
    return JSONResponse({"slots": slots})

# Simple healthcheck
@app.get("/health")
async def health():
    return {"status": "ok"}

# --- Scheduler: reminder job ---
scheduler = AsyncIOScheduler()

async def reminder_job():
    try:
        upcoming = sheets.get_lessons_within_minutes(REMINDER_MIN)
        if not upcoming:
            return
        for lesson in upcoming:
            # lesson is dict with fields including lesson_id, date_iso, time, tutor_id, student, amount, paid
            if str(lesson.get("paid", "")).lower() == "yes":
                continue
            lesson_id = lesson.get("lesson_id")
            tutor_id = int(lesson.get("tutor_id"))
            student = lesson.get("student")
            amount = float(lesson.get("amount") or 0)
            percent = sheets.get_tutor_percent(tutor_id) or 70.0
            payout = amount * percent / 100.0
            # send reminder through bot (via aiogram) - the bot instance is in bot_handlers module
            try:
                from bot_handlers import bot
                text_admin = (f"Напоминание (через {REMINDER_MIN} мин):\n"
                              f"Урок ID {lesson_id} — {lesson.get('date_iso')} {lesson.get('time')}\n"
                              f"Репетитор: {tutor_id}\n"
                              f"Ученик: {student}\n"
                              f"Сумма: {amount} ₽ → К выплате: {payout:.2f} ₽\n\n"
                              f"Если перевели: /pay {lesson_id}")
                await bot.send_message(ADMIN_ID, text_admin)
                # try notify tutor
                try:
                    await bot.send_message(tutor_id, f"Напоминание: у вас урок с {student} в {lesson.get('time')}.")
                except Exception:
                    pass
            except Exception:
                logger.exception("Failed to send reminder via bot")
    except Exception:
        logger.exception("Error in reminder_job")

# start scheduler
scheduler.add_job(lambda: asyncio.create_task(reminder_job()), "interval", seconds=60)
scheduler.start()

# Start bot in background
async def start_services():
    # start aiogram bot loop
    await start_bot(sheets)

if __name__ == "__main__":
    # Run bot and webapp together via uvicorn
    # start the bot in an asyncio task inside uvicorn on startup
    import threading

    def run_uvicorn():
        uvicorn.run("main:app", host="0.0.0.0", port=int(os.getenv("PORT", 8000)), log_level="info")

    # run uvicorn in main thread (so Render can use it)
    # but we must start bot as background task when app starts - bot_handlers.start_bot does that when called
    # For simplicity, we start uvicorn; bot is started from within bot_handlers when imported/initialized.
    run_uvicorn()

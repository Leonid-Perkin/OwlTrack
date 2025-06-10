import logging
from datetime import datetime, timedelta
from aiogram import Bot, Dispatcher, types
from aiogram.types import Message
from aiogram.utils import executor
from dateutil import parser
import requests
from typing import List, Tuple, Optional

# === rasp_api.py ===
class YandexRaspAPI:
    BASE_URL = "https://api.rasp.yandex.net/v3.0/search/"

    def __init__(self, api_key: str):
        self.api_key = api_key

    def get_schedule(self, from_code: str, to_code: str, date: str, page_size: int = 2000) -> List[Tuple[str, str, str, Optional[str]]]:
        params = {
            "apikey": self.api_key,
            "from": from_code,
            "to": to_code,
            "date": date,
            "format": "json",
            "lang": "ru_RU",
            "limit": page_size
        }
        try:
            response = requests.get(self.BASE_URL, params=params, timeout=10)
            response.raise_for_status()
            segments = response.json().get("segments", [])
            result = []
            for seg in segments:
                if not (seg.get("departure") and seg.get("arrival")):
                    continue
                title = seg.get("thread", {}).get("title", "Неизвестно")
                if ("Пушкино" in title or "Москва (Ярославский вокзал)" in title):
                    result.append((
                        title,
                        seg["departure"],
                        seg["arrival"],
                        seg.get("thread", {}).get("express_type")
                    ))
            return result
        except requests.RequestException as e:
            print(f"❌ API Error: {e}")
            return []

def format_duration(start: str, end: str) -> str:
    try:
        start_dt = parser.isoparse(start)
        end_dt = parser.isoparse(end)
        duration = (end_dt - start_dt).total_seconds() / 60
        hours = int(duration // 60)
        minutes = int(duration % 60)
        return f"{hours:02d}:{minutes:02d}"
    except Exception:
        return "??:??"

def print_schedule(title: str, schedule: List[Tuple[str, str, str, Optional[str]]]) -> str:
    if not schedule:
        return f"\n=== {title} ===\nНет данных"
    lines = [f"\n=== {title} ==="]
    for train, dep, arr, express in schedule:
        dep_time = parser.isoparse(dep).strftime("%H:%M")
        arr_time = parser.isoparse(arr).strftime("%H:%M")
        duration = format_duration(dep, arr)
        label = "[ЭКСПРЕСС]" if express == "express" else "[ОБЫЧНАЯ]"
        lines.append(f"🚆 {label} {train}: {dep_time} → {arr_time} ⏱️ {duration}")
    return "\n".join(lines)

def find_fastest(schedule: List[Tuple[str, str, str, Optional[str]]], start_time: datetime, use_buffer: bool) -> Optional[Tuple[str, str, str, Optional[str]]]:
    filter_time = start_time + timedelta(minutes=30) if use_buffer else start_time
    future_trains = [seg for seg in schedule if parser.isoparse(seg[1]) >= filter_time]
    if not future_trains:
        return None
    def train_score(seg):
        dep = parser.isoparse(seg[1])
        arr = parser.isoparse(seg[2])
        duration = (arr - dep).total_seconds() / 60
        wait = (dep - filter_time).total_seconds() / 60
        return (wait, duration)
    return min(future_trains, key=train_score, default=None)

# === main bot ===
logging.basicConfig(level=logging.INFO)

bot = Bot(token=Config.BOT_TOKEN)
dp = Dispatcher(bot)

api = YandexRaspAPI(Config.API_KEY)
use_buffer = {"value": False}  # Состояние буфера (используется через замыкание)

@dp.message_handler(commands=['start'])
async def start(message: Message):
    await message.reply(
        "Привет! Я бот для просмотра расписания электричек:\n"
        "/to_moscow — Пушкино → Москва\n"
        "/to_pushkino — Москва → Пушкино\n"
        "/fast_to_moscow — ближайшая электричка в Москву\n"
        "/fast_to_pushkino — ближайшая электричка в Пушкино\n"
        "/toggle_buffer — переключить 30-минутный буфер"
    )

@dp.message_handler(commands=['to_moscow'])
async def to_moscow(message: Message):
    today = datetime.now().strftime("%Y-%m-%d")
    schedule = api.get_schedule(Config.STATION_Pushkino, Config.STATION_MOSCOW, today)
    text = print_schedule("Пушкино → Москва", schedule)
    await message.reply(text)

@dp.message_handler(commands=['to_pushkino'])
async def to_pushkino(message: Message):
    today = datetime.now().strftime("%Y-%m-%d")
    schedule = api.get_schedule(Config.STATION_MOSCOW, Config.STATION_Pushkino, today)
    text = print_schedule("Москва → Пушкино", schedule)
    await message.reply(text)

@dp.message_handler(commands=['fast_to_moscow'])
async def fast_to_moscow(message: Message):
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now()
    schedule = api.get_schedule(Config.STATION_Pushkino, Config.STATION_MOSCOW, today)
    fastest = find_fastest(schedule, now, use_buffer["value"])
    if fastest:
        text = print_schedule("Самая быстрая электричка → Москва", [fastest])
    else:
        text = "⚠️ Нет подходящих электричек."
    await message.reply(text)

@dp.message_handler(commands=['fast_to_pushkino'])
async def fast_to_pushkino(message: Message):
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now()
    schedule = api.get_schedule(Config.STATION_MOSCOW, Config.STATION_Pushkino, today)
    fastest = find_fastest(schedule, now, use_buffer["value"])
    if fastest:
        text = print_schedule("Самая быстрая электричка → Пушкино", [fastest])
    else:
        text = "⚠️ Нет подходящих электричек."
    await message.reply(text)

@dp.message_handler(commands=['toggle_buffer'])
async def toggle_buffer(message: Message):
    use_buffer["value"] = not use_buffer["value"]
    state = "включён" if use_buffer["value"] else "выключен"
    await message.reply(f"Буфер в 30 минут {state}.")

if __name__ == '__main__':
    executor.start_polling(dp, skip_updates=True)
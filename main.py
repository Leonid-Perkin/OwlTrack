from datetime import datetime, timedelta
import requests
from typing import List, Tuple, Optional
from dateutil import parser
from config import Config

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
                if ("Пушкино" in title or "Москва (Ярославский вокзал)" in title) or to_code == Config.STATION_Pushkino or from_code == Config.STATION_Pushkino:
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
        if end_dt < start_dt:
            print(f"WARNING: Arrival time {end} is earlier than departure time {start}")
            return "Invalid duration"
        duration = (end_dt - start_dt).total_seconds() / 60
        hours = int(duration // 60)
        minutes = int(duration % 60)
        if duration < 10 or duration > 120:
            print(f"WARNING: Unusual duration {hours:02d}:{minutes:02d} for {start} → {end}")
        return f"{hours:02d}:{minutes:02d}"
    except ValueError as e:
        print(f"ERROR: Invalid date format - Start: {start}, End: {end}, Error: {e}")
        return "Invalid format"

def print_schedule(title: str, schedule: List[Tuple[str, str, str, Optional[str]]]) -> None:
    print(f"\n=== {title} ===")
    if not schedule:
        print("Нет данных")
        return
    for train, dep, arr, express in schedule:
        dep_time = parser.isoparse(dep).strftime("%H:%M")
        arr_time = parser.isoparse(arr).strftime("%H:%M")
        duration = format_duration(dep, arr)
        label = "[ЭКСПРЕСС]" if express == "express" else "[ОБЫЧНАЯ]"
        print(f"🚆 {label} {train}: {dep_time} → {arr_time} ⏱️ {duration}")

def find_fastest(schedule: List[Tuple[str, str, str, Optional[str]]], start_time: datetime, use_buffer: bool) -> Optional[Tuple[str, str, str, Optional[str]]]:
    filter_time = start_time + timedelta(minutes=30) if use_buffer else start_time
    future_trains = [
        seg for seg in schedule
        if parser.isoparse(seg[1]) >= filter_time
    ]
    if not future_trains:
        return None

    def train_score(seg):
        dep = parser.isoparse(seg[1])
        arr = parser.isoparse(seg[2])
        duration = (arr - dep).total_seconds() / 60
        wait = (dep - filter_time).total_seconds() / 60
        if duration < 30 or duration > 60:
            return (float('inf'), wait)
        return (wait, duration)

    return min(future_trains, key=train_score, default=None)

def main():
    api = YandexRaspAPI(Config.API_KEY)
    today = datetime.now().strftime("%Y-%m-%d")
    now = datetime.now().astimezone()
    use_buffer = False

    schedule_to = api.get_schedule(Config.STATION_Pushkino, Config.STATION_MOSCOW, today)
    schedule_back = api.get_schedule(Config.STATION_MOSCOW, Config.STATION_Pushkino, today)

    while True:
        print(f"\n📋 Меню (Запас 30 минут: {'Включён' if use_buffer else 'Выключен'}):")
        print("1. Расписание: Пушкино → Москва")
        print("2. Расписание: Москва → Пушкино")
        print("3. Самая быстрая электричка от текущего времени → Москва")
        print("4. Самая быстрая электричка от текущего времени → Пушкино")
        print("5. Переключить запас 30 минут")
        print("0. Выход")

        choice = input("Выберите опцию: ")

        if choice == "1":
            print_schedule("Пушкино → Москва (Ярославский вокзал)", schedule_to)
        elif choice == "2":
            print_schedule("Москва (Ярославский вокзал) → Пушкино", schedule_back)
        elif choice == "3":
            fastest = find_fastest(schedule_to, now, use_buffer)
            if fastest:
                print_schedule("Самая быстрая электричка → Москва", [fastest])
            else:
                print("⚠️ Нет подходящих электричек.")
        elif choice == "4":
            fastest = find_fastest(schedule_back, now, use_buffer)
            if fastest:
                print_schedule("Самая быстрая электричка → Пушкино", [fastest])
            else:
                print("⚠️ Нет подходящих электричек.")
        elif choice == "5":
            use_buffer = not use_buffer
            print(f"Запас 30 минут {'включён' if use_buffer else 'выключен'}.")
        elif choice == "0":
            print("До свидания!")
            break
        else:
            print("❌ Неверный ввод.")
            
if __name__ == "__main__":
    main()
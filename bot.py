import asyncio
import sqlite3

from aiogram import Bot, Dispatcher, types
from aiogram.filters import Command
from aiogram.types import InlineKeyboardMarkup, InlineKeyboardButton

import os
BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

# =========================
# 💾 DATABASE
# =========================
conn = sqlite3.connect("fitness.db")
cursor = conn.cursor()

cursor.execute("""
CREATE TABLE IF NOT EXISTS progress (
    user_id INTEGER PRIMARY KEY,
    day TEXT,
    exercise_index INTEGER,
    set_number INTEGER
)
""")
conn.commit()


def save_progress(user_id, state):
    cursor.execute("""
    INSERT INTO progress (user_id, day, exercise_index, set_number)
    VALUES (?, ?, ?, ?)
    ON CONFLICT(user_id) DO UPDATE SET
        day=excluded.day,
        exercise_index=excluded.exercise_index,
        set_number=excluded.set_number
    """, (
        user_id,
        state.get("day"),
        state.get("exercise_index", 0),
        state.get("set", 1)
    ))
    conn.commit()


def load_progress(user_id):
    cursor.execute("SELECT day, exercise_index, set_number FROM progress WHERE user_id=?", (user_id,))
    row = cursor.fetchone()

    if row:
        return {
            "day": row[0],
            "exercise_index": row[1],
            "set": row[2],
            "paused": False,
            "resting": False,
            "message_id": None
        }
    return None


# =========================
# 🧠 STATE
# =========================
user_state = {}

# =========================
# 🏋️ WORKOUTS
# =========================
workouts = {
    "day_mon": [
        {"name": "Жим штанги лёжа", "sets": 4, "rest": 120},
        {"name": "Жим гантелей наклон", "sets": 3, "rest": 90},
        {"name": "Разводка гантелей", "sets": 3, "rest": 60},
    ],
    "day_wed": [
        {"name": "Подтягивания", "sets": 4, "rest": 120},
        {"name": "Тяга в Смите", "sets": 4, "rest": 120},
        {"name": "Верхний блок", "sets": 3, "rest": 90},
    ],
    "day_fri": [
        {"name": "Присед", "sets": 4, "rest": 150},
        {"name": "Жим ногами", "sets": 3, "rest": 120},
        {"name": "Подъёмы на носки", "sets": 4, "rest": 60},
    ],
}

# =========================
# 🎛 KEYBOARDS
# =========================
def get_days_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [
            InlineKeyboardButton(text="ПН", callback_data="day_mon"),
            InlineKeyboardButton(text="СР", callback_data="day_wed"),
            InlineKeyboardButton(text="ПТ", callback_data="day_fri"),
        ]
    ])


def get_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="✅ Сделал", callback_data="next")],
        [
            InlineKeyboardButton(text="▶️", callback_data="resume"),
            InlineKeyboardButton(text="⏸", callback_data="pause"),
        ],
        [
            InlineKeyboardButton(text="🔄", callback_data="restart"),
            InlineKeyboardButton(text="🏁", callback_data="finish"),
        ]
    ])


# =========================
# 📊 BAR
# =========================
def bar(i, total):
    p = int((i / total) * 10)
    return "█" * p + "░" * (10 - p)


# =========================
# 📱 UI RENDER (ONE MESSAGE)
# =========================
async def render(message, user_id):
    state = user_state[user_id]
    day = state["day"]

    ex_list = workouts[day]

    if state["exercise_index"] >= len(ex_list):
        await bot.edit_message_text(
            "🏁 Тренировка завершена 💪",
            chat_id=message.chat.id,
            message_id=state["message_id"]
        )
        return

    ex = ex_list[state["exercise_index"]]

    text = (
        f"🏋️ {ex['name']}\n"
        f"Подход: {state['set']}/{ex['sets']}\n"
        f"Прогресс: [{bar(state['exercise_index'], len(ex_list))}]\n\n"
        f"{'⏸ ПАУЗА' if state.get('paused') else '▶️ СТАРТ ПОДХОДА'}\n"
        f"{'⏳ ОТДЫХ...' if state.get('resting') else ''}"
    )

    keyboard = get_keyboard()

    if state["message_id"] is None:
        msg = await message.answer(text, reply_markup=keyboard)
        state["message_id"] = msg.message_id
    else:
        await bot.edit_message_text(
            text,
            chat_id=message.chat.id,
            message_id=state["message_id"],
            reply_markup=keyboard
        )


# =========================
# 🚀 START
# =========================
@dp.message(Command("start"))
async def start(message: types.Message):
    user_id = message.from_user.id

    saved = load_progress(user_id)

    if saved:
        user_state[user_id] = saved
        await message.answer("🔄 Прогресс восстановлен")
        await render(message, user_id)
    else:
        await message.answer("Выбери день:", reply_markup=get_days_keyboard())


# =========================
# 📅 DAY SELECT
# =========================
@dp.callback_query(lambda c: c.data.startswith("day_"))
async def choose(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    user_state[user_id] = {
        "day": callback.data,
        "exercise_index": 0,
        "set": 1,
        "paused": False,
        "resting": False,
        "message_id": None
    }

    save_progress(user_id, user_state[user_id])

    await render(callback.message, user_id)
    await callback.answer()


# =========================
# ❗ NEXT SET (WITH TIMER FIX)
# =========================
@dp.callback_query(lambda c: c.data == "next")
async def next_set(callback: types.CallbackQuery):
    user_id = callback.from_user.id
    state = user_state[user_id]

    if state.get("paused"):
        await callback.answer("⏸ Пауза", show_alert=True)
        return

    if state.get("resting"):
        await callback.answer("⏳ Отдых идёт", show_alert=True)
        return

    day = state["day"]
    ex_list = workouts[day]
    ex = ex_list[state["exercise_index"]]

    state["resting"] = True

    # ➜ логика подходов
    if state["set"] < ex["sets"]:
        state["set"] += 1
        rest_time = ex["rest"]
    else:
        state["exercise_index"] += 1
        state["set"] = 1

        if state["exercise_index"] >= len(ex_list):
            await render(callback.message, user_id)
            await callback.message.answer("🏁 Тренировка завершена 💪")
            return

        rest_time = ex_list[state["exercise_index"]]["rest"]

    save_progress(user_id, state)

    await render(callback.message, user_id)
    await callback.answer()

    asyncio.create_task(rest_timer(callback.message, user_id, rest_time))


# =========================
# ⏱ TIMER
# =========================
async def rest_timer(message, user_id, seconds):
    await asyncio.sleep(seconds)

    if user_id in user_state:
        state = user_state[user_id]
        state["resting"] = False

        # 🔔 отправляем уведомление
        msg = await bot.send_message(
            user_id,
            "🏁 Отдых завершён — начинай подход 💪"
        )

        # ⏳ даём Telegram отправить push
        await asyncio.sleep(1.5)

        # 🧹 удаляем сообщение (чтобы не было спама)
        try:
            await bot.delete_message(user_id, msg.message_id)
        except:
            pass

        # 📱 обновляем UI (одно сообщение)
        await render(message, user_id)


# =========================
# 🎛 CONTROLS
# =========================
@dp.callback_query(lambda c: c.data == "pause")
async def pause(callback: types.CallbackQuery):
    user_state[callback.from_user.id]["paused"] = True
    await render(callback.message, callback.from_user.id)
    await callback.answer()


@dp.callback_query(lambda c: c.data == "resume")
async def resume(callback: types.CallbackQuery):
    user_state[callback.from_user.id]["paused"] = False
    await render(callback.message, callback.from_user.id)
    await callback.answer()


@dp.callback_query(lambda c: c.data == "restart")
async def restart(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    user_state[user_id] = {
        "day": None,
        "exercise_index": 0,
        "set": 1,
        "paused": False,
        "resting": False,
        "message_id": None
    }

    cursor.execute("DELETE FROM progress WHERE user_id=?", (user_id,))
    conn.commit()

    await callback.message.answer("🔄 Сброс. Выбери день:", reply_markup=get_days_keyboard())
    await callback.answer()


@dp.callback_query(lambda c: c.data == "finish")
async def finish(callback: types.CallbackQuery):
    user_id = callback.from_user.id

    user_state.pop(user_id, None)
    cursor.execute("DELETE FROM progress WHERE user_id=?", (user_id,))
    conn.commit()

    await callback.message.answer("🏁 Завершено 💪")
    await callback.answer()


# =========================
# ▶️ RUN
# =========================
async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
import asyncio
import os
from aiogram import Bot, Dispatcher, F
from aiogram.types import Message, CallbackQuery, InlineKeyboardMarkup, InlineKeyboardButton
from aiogram.filters import Command

BOT_TOKEN = os.getenv("BOT_TOKEN")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher()

user_state = {}

# ================= ПРОГРАММА =================

WORKOUTS = {
    "mon": [
        {"name": "Жим штанги лёжа", "sets": 4, "rest": 120},
        {"name": "Жим гантелей на наклонной", "sets": 3, "rest": 90},
        {"name": "Разводка гантелей лёжа", "sets": 3, "rest": 60},
        {"name": "Брусья", "sets": 3, "rest": 90},
        {"name": "Подъём штанги на бицепс", "sets": 3, "rest": 90},
        {"name": "Подъём штанги в Скотте", "sets": 3, "rest": 90},
        {"name": "Молотковые сгибания", "sets": 3, "rest": 60},
        {"name": "Сгибания кистей", "sets": 3, "rest": 60},
        {"name": "Обратные сгибания", "sets": 3, "rest": 60},
    ],
    "wed": [
        {"name": "Подтягивания", "sets": 4, "rest": 120},
        {"name": "Тяга в Смите к груди", "sets": 4, "rest": 120},
        {"name": "Верхний блок к груди", "sets": 3, "rest": 90},
        {"name": "Горизонтальная тяга", "sets": 3, "rest": 90},
        {"name": "Гиперэкстензия", "sets": 3, "rest": 60},
        {"name": "Жим узким хватом", "sets": 3, "rest": 120},
        {"name": "Разгибание на блоке", "sets": 3, "rest": 60},
        {"name": "Французский жим", "sets": 3, "rest": 90},
    ],
    "fri": [
        {"name": "Присед", "sets": 4, "rest": 150},
        {"name": "Жим ногами", "sets": 3, "rest": 120},
        {"name": "Сгибание ног в тренажёре", "sets": 3, "rest": 90},
        {"name": "Подъёмы на носки", "sets": 4, "rest": 60},
    ]
}

DAY_NAMES = {
    "mon": "Понедельник — Грудь + Бицепс",
    "wed": "Среда — Спина + Трицепс",
    "fri": "Пятница — Ноги + Дельты"
}

# ================= UI =================

def progress_bar(index, total):
    return "🟩" * index + "⬜" * (total - index)

def format_time(sec):
    return f"{sec//60:02d}:{sec%60:02d}"

def day_keyboard():
    return InlineKeyboardMarkup(inline_keyboard=[
        [InlineKeyboardButton(text="ПН", callback_data="day_mon"),
         InlineKeyboardButton(text="СР", callback_data="day_wed"),
         InlineKeyboardButton(text="ПТ", callback_data="day_fri")]
    ])

def get_keyboard(state):
    if state["mode"] == "choose":
        return day_keyboard()

    if state["mode"] == "training":
        if state.get("resting"):
            return InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text=f"⏳ {format_time(state['rest_left'])}", callback_data="noop")],
                [InlineKeyboardButton(text="⏭ Пропустить отдых", callback_data="skip_rest")],
                [InlineKeyboardButton(text="🔄 Рестарт", callback_data="restart"),
                 InlineKeyboardButton(text="🏁 Завершить", callback_data="finish")]
            ])
        else:
            return InlineKeyboardMarkup(inline_keyboard=[
                [InlineKeyboardButton(text="✅ Сделал", callback_data="done"),
                 InlineKeyboardButton(text="⏭ Пропустить", callback_data="skip")],
                [InlineKeyboardButton(text="🔄 Рестарт", callback_data="restart"),
                 InlineKeyboardButton(text="🏁 Завершить", callback_data="finish")]
            ])

async def render(chat_id):
    state = user_state[chat_id]

    if state["mode"] == "choose":
        text = "📅 Выбери день тренировки"
    else:
        ex = state["ex_list"][state["exercise_index"]]

        status = (
            f"⏳ Отдых: {format_time(state['rest_left'])}"
            if state.get("resting") else "▶️ РАБОТА"
        )

        text = (
            f"📅 {state['day_name']}\n\n"
            f"🏋️ {ex['name']}\n"
            f"Подход: {state['set']}/{ex['sets']}\n"
            f"Прогресс: [{progress_bar(state['exercise_index'], len(state['ex_list']))}]\n\n"
            f"{status}"
        )

    kb = get_keyboard(state)

    if state["message_id"] is None:
        msg = await bot.send_message(chat_id, text, reply_markup=kb)
        state["message_id"] = msg.message_id
    else:
        await bot.edit_message_text(
            text,
            chat_id=chat_id,
            message_id=state["message_id"],
            reply_markup=kb
        )

# ================= ЛОГИКА =================

async def start_day(chat_id, day):
    user_state[chat_id] = {
        "mode": "training",
        "day": day,
        "day_name": DAY_NAMES[day],
        "exercise_index": 0,
        "set": 1,
        "resting": False,
        "rest_left": 0,
        "message_id": None,
        "timer_task": None,
        "ex_list": WORKOUTS[day]
    }
    await render(chat_id)

async def countdown(chat_id):
    state = user_state[chat_id]

    while state["rest_left"] > 0:
        await asyncio.sleep(1)
        if chat_id not in user_state:
            return

        state["rest_left"] -= 1
        await render(chat_id)

    state["resting"] = False

    notify = await bot.send_message(chat_id, "⏰ Отдых окончен!")
    asyncio.create_task(delete_later(chat_id, notify.message_id, 12))

    await render(chat_id)

async def delete_later(chat_id, message_id, delay):
    await asyncio.sleep(delay)
    try:
        await bot.delete_message(chat_id, message_id)
    except:
        pass

async def start_rest(chat_id, seconds):
    state = user_state[chat_id]

    state["resting"] = True
    state["rest_left"] = seconds

    if state.get("timer_task"):
        state["timer_task"].cancel()

    await render(chat_id)
    state["timer_task"] = asyncio.create_task(countdown(chat_id))

async def finish_workout(chat_id):
    state = user_state.get(chat_id)
    if not state:
        return

    if state.get("timer_task"):
        state["timer_task"].cancel()

    try:
        await bot.delete_message(chat_id, state["message_id"])
    except:
        pass

    user_state[chat_id] = {"mode": "choose", "message_id": None}

# ================= HANDLERS =================

@dp.message(Command("start"))
async def cmd_start(message: Message):
    user_state[message.chat.id] = {"mode": "choose", "message_id": None}
    await render(message.chat.id)

@dp.callback_query(F.data.startswith("day_"))
async def day_select(callback: CallbackQuery):
    day = callback.data.split("_")[1]
    await start_day(callback.message.chat.id, day)
    await callback.answer()

@dp.callback_query(F.data == "done")
async def done_cb(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    state = user_state[chat_id]

    if state.get("resting"):
        return

    ex = state["ex_list"][state["exercise_index"]]

    if state["set"] < ex["sets"]:
        state["set"] += 1
    else:
        state["exercise_index"] += 1
        state["set"] = 1

        if state["exercise_index"] >= len(state["ex_list"]):
            await finish_workout(chat_id)
            await callback.answer("Тренировка завершена")
            return

    await start_rest(chat_id, ex["rest"])
    await callback.answer()

@dp.callback_query(F.data == "skip")
async def skip_cb(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    state = user_state[chat_id]

    state["exercise_index"] += 1
    state["set"] = 1

    if state["exercise_index"] >= len(state["ex_list"]):
        await finish_workout(chat_id)
        await callback.answer("Тренировка завершена")
        return

    await render(chat_id)
    await callback.answer()

@dp.callback_query(F.data == "skip_rest")
async def skip_rest_cb(callback: CallbackQuery):
    chat_id = callback.message.chat.id
    state = user_state.get(chat_id)

    if not state or not state.get("resting"):
        return

    if state.get("timer_task"):
        state["timer_task"].cancel()

    state["resting"] = False
    state["rest_left"] = 0

    notify = await bot.send_message(chat_id, "⏩ Отдых пропущен")
    asyncio.create_task(delete_later(chat_id, notify.message_id, 8))

    await render(chat_id)
    await callback.answer()

@dp.callback_query(F.data == "restart")
async def restart_cb(callback: CallbackQuery):
    user_state[callback.message.chat.id] = {"mode": "choose", "message_id": None}
    await render(callback.message.chat.id)
    await callback.answer("Сброшено")

@dp.callback_query(F.data == "finish")
async def finish_cb(callback: CallbackQuery):
    await finish_workout(callback.message.chat.id)
    await callback.answer("Завершено")

@dp.callback_query(F.data == "noop")
async def noop_cb(callback: CallbackQuery):
    await callback.answer()

# ================= RUN =================

async def main():
    await dp.start_polling(bot)

if __name__ == "__main__":
    asyncio.run(main())
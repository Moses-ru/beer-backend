import os
import asyncio
import threading
from flask import Flask, request, jsonify
from aiogram import Bot, Dispatcher, types
from aiogram.types import BotCommand
from aiogram.fsm.storage.memory import MemoryStorage

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("Переменная окружения BOT_TOKEN не установлена")

bot = Bot(token=BOT_TOKEN)
dp = Dispatcher(storage=MemoryStorage())
app = Flask(__name__)

# Команды
@dp.message(lambda msg: msg.text == "/start")
async def cmd_start(message: types.Message):
    await message.answer("Привет! Нажми /play чтобы начать игру 🍻")

@dp.message(lambda msg: msg.text == "/play")
async def cmd_play(message: types.Message):
    await bot.send_game(
        chat_id=message.chat.id,
        game_short_name="beer_clicker"
    )

# Flask: приём очков
@app.route("/api/score", methods=["POST"])
def receive_score():
    data = request.json
    user_id = data.get("user_id")
    score = data.get("score")
    chat_id = data.get("chat_id")
    message_id = data.get("message_id")

    if not all([user_id, score, chat_id, message_id]):
        return jsonify({"error": "Missing fields"}), 400

    try:
        asyncio.run(bot.set_game_score(
            user_id=int(user_id),
            score=int(score),
            chat_id=int(chat_id),
            message_id=int(message_id),
            force=True
        ))
        return jsonify({"status": "ok"}), 200
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route("/")
def home():
    return "🏓 Bot is up and running!"

# 🔁 Асинхронный запуск aiogram polling
async def start_bot():
    await bot.set_my_commands([
        BotCommand(command="start", description="Запуск"),
        BotCommand(command="play", description="Играть в Beer Clicker 🍺")
    ])
    await dp.start_polling(bot)

# 🚀 Flask в отдельном потоке
def run_flask():
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

if __name__ == "__main__":
    threading.Thread(target=run_flask).start()
    asyncio.run(start_bot())

import os
import asyncio
from flask import Flask, request, jsonify
from aiogram import Bot

app = Flask(__name__)

# Получаем токен из переменной окружения
BOT_TOKEN = os.getenv("7574810395:AAH7-PqxhdvqBU9FbW8nkX1w1RLMQBdWf-4")
if not BOT_TOKEN:
    raise ValueError("Переменная окружения BOT_TOKEN не установлена")

bot = Bot(token=BOT_TOKEN)

@app.route("/")
def home():
    return "🏓 Bot is up and running!"

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
        # Асинхронно устанавливаем очки пользователю
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

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

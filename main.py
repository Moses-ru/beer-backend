from flask import Flask, request, jsonify
from aiogram import Bot
import os
import asyncio

app = Flask(__name__)
BOT_TOKEN = os.getenv("7574810395:AAH7-PqxhdvqBU9FbW8nkX1w1RLMQBdWf-4")
bot = Bot(token="7574810395:AAH7-PqxhdvqBU9FbW8nkX1w1RLMQBdWf-4")

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

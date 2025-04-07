
import os
import json
import asyncio
from flask import Flask, request, jsonify
from aiogram import Bot
from collections import defaultdict

SCORES_FILE = "scores.json"

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not set")

bot = Bot(token=BOT_TOKEN)
app = Flask(__name__)

# Загрузка сохранённых очков
if os.path.exists(SCORES_FILE):
    with open(SCORES_FILE, "r") as f:
        raw_scores = json.load(f)
        scores = defaultdict(int, {int(k): int(v) for k, v in raw_scores.items()})
else:
    scores = defaultdict(int)

def save_scores():
    with open(SCORES_FILE, "w") as f:
        json.dump(scores, f)

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
        scores[user_id] = max(scores[user_id], score)
        save_scores()  # сохраняем при обновлении

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

@app.route("/api/leaderboard", methods=["GET"])

import os
import sqlite3
import asyncio
from flask import Flask, request, jsonify
from aiogram import Bot

BOT_TOKEN = os.getenv("BOT_TOKEN")
if not BOT_TOKEN:
    raise ValueError("BOT_TOKEN not set")

bot = Bot(token=BOT_TOKEN)
app = Flask(__name__)

DB_FILE = "database.db"

def init_db():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("""
            CREATE TABLE IF NOT EXISTS scores (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                score INTEGER
            )
        """)
        conn.commit()

@app.route("/api/score", methods=["POST"])
def receive_score():
    data = request.json
    user_id = data.get("user_id")
    score = data.get("score")
    username = data.get("username") or "Unknown"
    chat_id = data.get("chat_id")
    message_id = data.get("message_id")

    if not all([user_id, score, chat_id, message_id]):
        return jsonify({"error": "Missing fields"}), 400

    try:
        # Обновим базу данных
        with sqlite3.connect(DB_FILE) as conn:
            c = conn.cursor()
            c.execute("""
                INSERT INTO scores (user_id, username, score) VALUES (?, ?, ?)
                ON CONFLICT(user_id) DO UPDATE SET score=excluded.score
                WHERE excluded.score > scores.score
            """, (user_id, username, score))
            conn.commit()

        # Отправим очки в Telegram
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
def get_leaderboard():
    with sqlite3.connect(DB_FILE) as conn:
        c = conn.cursor()
        c.execute("SELECT username, score FROM scores ORDER BY score DESC LIMIT 10")
        leaderboard = [{"username": row[0], "score": row[1]} for row in c.fetchall()]
    return jsonify(leaderboard)

@app.route("/")
def home():
    return "🏓 Bot is up and running!"

if __name__ == "__main__":
    init_db()
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)

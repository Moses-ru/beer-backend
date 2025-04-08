from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import os
import hashlib
import hmac
import urllib.parse

app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL")  # PostgreSQL URL from Render
BOT_TOKEN = os.environ.get("BOT_TOKEN")  # Telegram Bot Token


def get_connection():
    return psycopg2.connect(DATABASE_URL)


def init_db():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('''
                CREATE TABLE IF NOT EXISTS scores (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    score INTEGER
                )
            ''')
            conn.commit()

def check_init_data(init_data_raw):
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data_raw, strict_parsing=True))
        hash_from_telegram = parsed_data.pop("hash")

        # Telegram требует сортировки ключей по алфавиту
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        secret_key = hmac.new(BOT_TOKEN.encode(), b"WebAppData", hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        print("Telegram hash:", hash_from_telegram)
        print("Calculated hash:", calculated_hash)
        print("Data string:", data_check_string)

        return hmac.compare_digest(calculated_hash, hash_from_telegram)
    except Exception as e:
        print("Error validating initData:", e)
        return False


@app.route('/api/score', methods=['POST'])
def save_score():
    init_data_raw = request.headers.get("X-Telegram-Bot-InitData")
    print("🔹 Получен X-Telegram-Bot-InitData:", init_data_raw)

    if not init_data_raw or not check_init_data(init_data_raw):
        print("❌ initData не прошёл валидацию")
        return jsonify({"error": "Invalid init data"}), 403


    data = request.get_json()
    user_id = data.get('user_id')
    username = data.get('username', '')
    score = data.get('score', 0)

    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT score FROM scores WHERE user_id = %s', (user_id,))
            row = cur.fetchone()
            if row:
                if score > row[0]:
                    cur.execute('UPDATE scores SET score = %s, username = %s WHERE user_id = %s',
                                (score, username, user_id))
            else:
                cur.execute('INSERT INTO scores (user_id, username, score) VALUES (%s, %s, %s)',
                            (user_id, username, score))
            conn.commit()

    return jsonify({"status": "ok"})


@app.route('/api/leaderboard', methods=['GET'])
def leaderboard():
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute('SELECT user_id, username, score FROM scores ORDER BY score DESC LIMIT 10')
            rows = cur.fetchall()
            result = [{"user_id": uid, "username": username, "score": score} for uid, username, score in rows]
    return jsonify(result)


@app.route('/')
def index():
    return "\U0001F37A Beer Clicker backend with PostgreSQL is running!"


if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)

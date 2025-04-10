from flask import Flask, request, jsonify
from flask_cors import CORS
import psycopg2
import psycopg2.extras
import os
import hashlib
import hmac
import urllib.parse
import traceback

app = Flask(__name__)
CORS(app, origins=["https://moses-ru.github.io"])
CORS(app, resources={r"/api/*": {"origins": "*"}}, supports_credentials=True)

DATABASE_URL = os.environ.get("DATABASE_URL")
WEBAPP_SECRET = os.environ.get("WEBAPP_SECRET")

if not WEBAPP_SECRET:
    raise Exception("❌ WEBAPP_SECRET не задан в переменных окружения")

WEBAPP_SECRET = bytes.fromhex(WEBAPP_SECRET)

def get_connection():
    return psycopg2.connect(DATABASE_URL)

def init_db():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('''CREATE TABLE IF NOT EXISTS achievements (
                    user_id BIGINT PRIMARY KEY,
                    data JSONB
                );''')
                cur.execute('''CREATE TABLE IF NOT EXISTS scores (
                    user_id BIGINT PRIMARY KEY,
                    username TEXT,
                    score INTEGER
                );''')
                cur.execute('''CREATE TABLE IF NOT EXISTS processed_requests (
                    request_hash TEXT PRIMARY KEY
                );''')  # Таблица для хранения хешей обработанных запросов
                conn.commit()
        print("✅ Таблицы инициализированы")
    except Exception:
        print("🔥 Ошибка при инициализации БД:")
        traceback.print_exc()

def get_init_data_hash(init_data_raw):
    """Функция для получения хеша данных initData"""
    return hashlib.sha256(init_data_raw.encode('utf-8')).hexdigest()

def is_init_data_processed(init_data_hash):
    """Проверка, был ли уже обработан данный запрос"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM processed_requests WHERE request_hash = %s", (init_data_hash,))
            return cur.fetchone() is not None

def mark_request_as_processed(init_data_hash):
    """Помечаем запрос как обработанный"""
    with get_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("INSERT INTO processed_requests (request_hash) VALUES (%s)", (init_data_hash,))
            conn.commit()

def check_init_data(init_data_raw):
    try:
        parsed_data = dict(urllib.parse.parse_qsl(init_data_raw, strict_parsing=True))
        hash_from_telegram = parsed_data.pop("hash")

        # Убедитесь, что ключи отсортированы
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(parsed_data.items()))
        secret_key = hmac.new(WEBAPP_SECRET, b"WebAppData", hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

        print("🔍 data_check_string:", data_check_string)
        print("🔍 Calculated hash:", calculated_hash)
        print("🔍 Hash from Telegram:", hash_from_telegram)

        return hmac.compare_digest(calculated_hash, hash_from_telegram)
    except Exception:
        print("🔥 Ошибка в check_init_data:")
        traceback.print_exc()
        return False

init_db()

@app.route('/api/score', methods=['POST'])
def save_score():
    try:
        init_data_raw = request.headers.get("X-Telegram-Bot-InitData")
        if not init_data_raw or not check_init_data(init_data_raw):
            return jsonify({"error": "Invalid init data"}), 403

        data = request.get_json()
        user_id = data.get('user_id')
        username = data.get('username', '')
        score = data.get('score', 0)

        if not user_id:
            raise ValueError("Missing user_id")

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
    except Exception:
        print("🔥 Ошибка в save_score:")
        traceback.print_exc()
        return jsonify({"error": "Server error"}), 500

@app.route('/api/leaderboard', methods=['GET'])
def leaderboard():
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute('SELECT user_id, username, score FROM scores ORDER BY score DESC LIMIT 10')
                rows = cur.fetchall()
                result = [{"user_id": uid, "username": username, "score": score} for uid, username, score in rows]
        return jsonify(result)
    except Exception:
        print("🔥 Ошибка в leaderboard:")
        traceback.print_exc()
        return jsonify({"error": "Server error"}), 500

@app.route('/')
def index():
    return "🍺 Beer Clicker backend is running!"

@app.route('/api/achievements/<int:user_id>', methods=['GET'])
def get_achievements(user_id):
    try:
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM achievements WHERE user_id = %s", (user_id,))
                row = cur.fetchone()
                if row:
                    return jsonify(row[0])
        return jsonify({})
    except Exception:
        print("🔥 Ошибка в get_achievements:")
        traceback.print_exc()
        return jsonify({"error": "Server error"}), 500

@app.route('/api/achievements', methods=['GET', 'POST', 'OPTIONS'])
def handle_achievements():
    if request.method == 'OPTIONS':
        return '', 204

    init_data_raw = request.headers.get("X-Telegram-Bot-InitData")
    
    print("📦 Получен initData:")
    print(init_data_raw)
    
    if not init_data_raw or not check_init_data(init_data_raw):
        return jsonify({"error": "Invalid init data"}), 403

    # Получаем хеш запроса
    init_data_hash = get_init_data_hash(init_data_raw)
    
    # Проверяем, был ли уже обработан этот запрос
    if is_init_data_processed(init_data_hash):
        return jsonify({"error": "Request already processed"}), 400

    # Получаем данные из запроса
    if request.method == 'GET':
        parsed_data = dict(urllib.parse.parse_qsl(init_data_raw))
        user_id = parsed_data.get("user")
        if not user_id:
            return jsonify({"error": "Missing user ID"}), 400

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM achievements WHERE user_id = %s", (user_id,))
                row = cur.fetchone()
                return jsonify(row[0] if row else {})

    if request.method == 'POST':
        data = request.get_json()
        user_id = data.get("user_id")
        achievements = data.get("achievements")

        if not user_id or not isinstance(achievements, dict):
            return jsonify({"error": "Missing or invalid data"}), 400

        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO achievements (user_id, data)
                               VALUES (%s, %s)
                               ON CONFLICT (user_id) DO UPDATE SET data = EXCLUDED.data""",
                            (user_id, psycopg2.extras.Json(achievements)))
                conn.commit()

        # После обработки запроса помечаем его как обработанный
        mark_request_as_processed(init_data_hash)

        return jsonify({"status": "ok"})

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)

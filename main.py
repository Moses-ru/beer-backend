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
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("❌ BOT_TOKEN не задан")

# Преобразуем токен бота в ключ для проверки
WEBAPP_SECRET = hmac.new(
    key=b"WebAppData",
    msg=BOT_TOKEN.encode(),
    digestmod=hashlib.sha256
).digest()

def get_connection():
    return psycopg2.connect(DATABASE_URL)

@app.after_request
def after_request(response):
    response.headers["Access-Control-Allow-Origin"] = "*"
    response.headers["Access-Control-Allow-Methods"] = "*"
    response.headers["Access-Control-Allow-Headers"] = "*"
    return response

@app.route('/api/verify', methods=['POST'])
def verify_init_data():
    init_data = request.headers.get("X-Telegram-Bot-InitData", "")
    return jsonify({
        "status": "ok",
        "is_valid": check_init_data(init_data),
        "init_data_length": len(init_data),
        "bot_token_prefix": BOT_TOKEN[:5] + "..." + BOT_TOKEN[-5:]
    })

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
        if not init_data_raw:
            print("⚠️ Empty init_data_raw")
            return False

        # Декодируем URL-encoded строку только один раз
        init_data_raw = urllib.parse.unquote(init_data_raw)
        parsed_data = dict(urllib.parse.parse_qsl(init_data_raw, keep_blank_values=True))
        
        hash_from_telegram = parsed_data.pop("hash", "")
        if not hash_from_telegram:
            print("⚠️ No hash in init_data")
            return False

        # Удаляем ненужные поля
        parsed_data.pop("signature", None)

        # Формируем data_check_string в точном порядке
        required_fields = ['auth_date', 'query_id', 'user']
        data_check_string_parts = []
        
        for field in required_fields:
            if field in parsed_data:
                data_check_string_parts.append(f"{field}={parsed_data[field]}")
        
        data_check_string = "\n".join(data_check_string_parts)
        print("🔍 Data check string:", data_check_string)

        # Генерируем секретный ключ
        secret_key = hmac.new(
            key=b"WebAppData",
            msg=BOT_TOKEN.encode(),
            digestmod=hashlib.sha256
        ).digest()

        # Вычисляем хеш
        calculated_hash = hmac.new(
            key=secret_key,
            msg=data_check_string.encode(),
            digestmod=hashlib.sha256
        ).hexdigest()

        print(f"🔍 Calculated: {calculated_hash}")
        print(f"🔍 Telegram: {hash_from_telegram}")
        
        return hmac.compare_digest(calculated_hash, hash_from_telegram)
    except Exception as e:
        print(f"🔥 Error in check_init_data: {str(e)}")
        traceback.print_exc()
        return False
        
init_db()

@app.route('/api/score', methods=['OPTIONS', 'POST'])
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

@app.route('/api/leaderboard', methods=['OPTIONS', 'POST', 'GET'])
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

@app.after_request
def after_request(response):
    response.headers["Access-Control-Allow-Origin"] = "https://moses-ru.github.io"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Telegram-Bot-InitData"
    return response

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)

from flask import Flask, request, jsonify
from flask_cors import CORS
from auth import verify_telegram_auth
import psycopg2
import psycopg2.extras
import os
from datetime import datetime, timedelta
import pytz
import hashlib
import hmac
import urllib.parse
import traceback
import time
import json

def get_correct_time():
    tz = pytz.timezone('Asia/Yekaterinburg')
    return datetime.now(tz)



app = Flask(__name__)
CORS(app)

DATABASE_URL = os.environ.get("DATABASE_URL")

BOT_TOKEN = os.environ.get("BOT_TOKEN")
if not BOT_TOKEN:
    raise Exception("❌ BOT_TOKEN не задан")

def check_init_data(init_data_str):
    try:
        if not init_data_str:
            return False
            
        # Парсим данные
        init_data = dict(urllib.parse.parse_qsl(init_data_str))
        if 'hash' not in init_data:
            return False
            
        # Извлекаем hash и удаляем его из данных
        hash_from_telegram = init_data.pop('hash')
        
        # Формируем строку для проверки в правильном порядке
        data_check_string = "\n".join([
            f"auth_date={init_data['auth_date']}",
            f"query_id={init_data['query_id']}",
            f"user={init_data['user']}"
        ])
        
        # Проверяем время (допустимое расхождение 5 минут)
        auth_time = int(init_data['auth_date'])
        current_time = int(time.time())
        if abs(current_time - auth_time) > 300:
            return False
            
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
        
        return hmac.compare_digest(calculated_hash, hash_from_telegram)
    except Exception as e:
        print(f"Validation error: {e}")
        return False

# Преобразуем токен бота в ключ для проверки
WEBAPP_SECRET = hmac.new(
    key=b"WebAppData",
    msg=BOT_TOKEN.encode(),
    digestmod=hashlib.sha256
).digest()

def get_connection():
    return psycopg2.connect(DATABASE_URL)

# Эндпоинт для проверки времени
@app.route('/server_time')
def server_time():
    return f"Екатеринбург: {get_correct_time()}"

@app.after_request
def after_request(response):
    response.headers["Access-Control-Allow-Origin"] = "https://moses-ru.github.io"
    response.headers["Access-Control-Allow-Methods"] = "GET, POST, OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Content-Type, X-Telegram-Bot-InitData"
    return response
    
@app.route('/debug_auth', methods=['GET'])
def debug_auth():
    init_data = request.args.get('initData') or request.headers.get('X-Telegram-InitData')
    
    if not init_data:
        return jsonify({"error": "Missing initData"}), 400

    try:
        auth_data = verify_telegram_auth(init_data)
        return jsonify({
            "status": "ok",
            "auth_data": auth_data
        })
    except Exception as e:
        return jsonify({
            "status": "error",
            "message": str(e)
        }), 403

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

def check_init_data(init_data_raw):
    try:
        if not init_data_raw:
            print("⚠️ Empty init_data_raw")
            return False

        # 1. Декодируем URL-encoded строку (только один раз!)
        init_data_raw = urllib.parse.unquote(init_data_raw)
        parsed_data = dict(urllib.parse.parse_qsl(init_data_raw, keep_blank_values=True))
        
        # 2. Проверка обязательных полей
        required_fields = {'auth_date', 'query_id', 'user', 'hash'}
        if not required_fields.issubset(parsed_data.keys()):
            print(f"⚠️ Missing fields in init_data: {parsed_data.keys()}")
            return False

        hash_from_telegram = parsed_data.pop("hash")
        
        # 3. Проверка времени (добавляем точную проверку часового пояса)
        auth_time = datetime.fromtimestamp(int(parsed_data['auth_date']), pytz.utc)
        server_time = datetime.now(pytz.timezone('Asia/Yekaterinburg'))
        
        if (server_time - auth_time) > timedelta(minutes=5):
            print(f"⚠️ Time mismatch: Server={server_time} (UTC+5) vs Auth={auth_time} (UTC)")
            return False

        # 4. Формируем data_check_string в строгом порядке
        data_check_string = "\n".join([
            f"auth_date={parsed_data['auth_date']}",
            f"query_id={parsed_data['query_id']}",
            f"user={parsed_data['user']}"
        ])

        # 5. Генерация ключа с улучшенной обработкой ошибок
        try:
            secret_key = hmac.new(
                key=b"WebAppData",
                msg=BOT_TOKEN.encode(),
                digestmod=hashlib.sha256
            ).digest()
            
            calculated_hash = hmac.new(
                key=secret_key,
                msg=data_check_string.encode(),
                digestmod=hashlib.sha256
            ).hexdigest()
        except Exception as hmac_error:
            print(f"🔥 HMAC generation error: {hmac_error}")
            return False

        # 6. Безопасное сравнение хешей
        return hmac.compare_digest(calculated_hash, hash_from_telegram)
        
    except Exception as e:
        print(f"🔥 Critical error in check_init_data: {str(e)}")
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
        username = data.get('username') or data.get('first_name') or f"user_{user_id}"
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

@app.route("/api/achievements/<int:user_id>", methods=["GET"])
def get_achievements(user_id):
    init_data = request.headers.get('X-Telegram-Bot-InitData')
    
    if not check_init_data(init_data):
        return jsonify({"error": "Invalid authentication"}), 403
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
    return jsonify({"status": "success"})

@app.route('/api/achievements', methods=['GET', 'OPTIONS'])
def handle_achievements():
    if request.method == 'OPTIONS':
        return '', 204
    
    init_data_raw = request.headers.get("X-Telegram-Bot-InitData")
    
    # Проверка аутентификации
    if not init_data_raw or not check_init_data(init_data_raw):
        return jsonify({"error": "Invalid init data"}), 403
    
    try:
        # Парсим user_id из initData
        parsed_data = dict(urllib.parse.parse_qsl(init_data_raw))
        user = parsed_data.get('user')
        if not user:
            return jsonify({"error": "Missing user data"}), 400
            
        # Парсим JSON user
        try:
            user_data = json.loads(user)
            user_id = user_data.get('id')
        except json.JSONDecodeError:
            return jsonify({"error": "Invalid user data format"}), 400
        
        # Получаем achievements из БД
        with get_connection() as conn:
            with conn.cursor() as cur:
                cur.execute("SELECT data FROM achievements WHERE user_id = %s", (user_id,))
                row = cur.fetchone()
                return jsonify(row[0] if row else {})
                
    except Exception as e:
        print(f"Error in achievements handler: {e}")
        return jsonify({"error": "Server error"}), 500

        # После обработки запроса помечаем его как обработанный
        mark_request_as_processed(init_data_hash)

        return jsonify({"status": "ok"})

@app.route('/debug_auth', methods=['POST'])
def debug_auth():
    return jsonify({
        "headers": dict(request.headers),
        "init_data": request.headers.get('X-Telegram-Bot-InitData'),
        "server_time": int(time.time()),
        "bot_token": BOT_TOKEN[:5] + "..." + BOT_TOKEN[-5:]
    })

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)

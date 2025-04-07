from flask import Flask, request, jsonify
from flask_cors import CORS
import sqlite3
import os

app = Flask(__name__)
CORS(app)

DB_PATH = 'scores.db'

# Создание базы и таблицы при первом запуске
def init_db():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS scores (
                user_id INTEGER PRIMARY KEY,
                username TEXT,
                score INTEGER
            )
        ''')
        conn.commit()

@app.route('/api/score', methods=['POST'])
def save_score():
    data = request.get_json()
    user_id = data.get('user_id')
    username = data.get('username', '')
    score = data.get('score', 0)

    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT score FROM scores WHERE user_id = ?', (user_id,))
        row = cursor.fetchone()
        if row:
            if score > row[0]:  # Обновляем только если счёт больше
                cursor.execute('UPDATE scores SET score = ?, username = ? WHERE user_id = ?', (score, username, user_id))
        else:
            cursor.execute('INSERT INTO scores (user_id, username, score) VALUES (?, ?, ?)', (user_id, username, score))
        conn.commit()

    return jsonify({"status": "ok"})

@app.route('/api/leaderboard', methods=['GET'])
def leaderboard():
    with sqlite3.connect(DB_PATH) as conn:
        cursor = conn.cursor()
        cursor.execute('SELECT user_id, username, score FROM scores ORDER BY score DESC LIMIT 10')
        rows = cursor.fetchall()
        result = [{"user_id": uid, "username": username, "score": score} for uid, username, score in rows]
    return jsonify(result)

@app.route('/')
def index():
    return "\U0001F37A Beer Clicker backend is running!"

if __name__ == '__main__':
    init_db()
    port = int(os.environ.get('PORT', 5000))
    app.run(debug=True, host='0.0.0.0', port=port)

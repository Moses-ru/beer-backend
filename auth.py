import hmac
import hashlib
import time
from urllib.parse import parse_qsl

BOT_TOKEN = "7574810395:AAH7-PqxhdvqBU9FbW8nkX1w1RLMQBdWf-4"

def verify_telegram_auth(init_data: str, max_age_seconds: int = 86400):
    data_check_arr = []
    parsed_data = dict(parse_qsl(init_data, keep_blank_values=True))

    auth_hash = parsed_data.pop('hash', None)
    if not auth_hash:
        raise ValueError("Missing hash in initData")

    for key, value in sorted(parsed_data.items()):
        data_check_arr.append(f"{key}={value}")

    data_check_string = '\n'.join(data_check_arr)
    secret_key = hashlib.sha256(BOT_TOKEN.encode()).digest()
    calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()

    if calculated_hash != auth_hash:
        raise ValueError("Invalid hash (possible forgery)")

    # Проверка на устаревание (опционально)
    auth_date = int(parsed_data.get("auth_date", 0))
    if time.time() - auth_date > max_age_seconds:
        raise ValueError("initData is too old")

    return parsed_data

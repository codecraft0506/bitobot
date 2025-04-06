import requests
import time
import hmac
import hashlib
import base64
import json
import os
from dotenv import load_dotenv

load_dotenv()

# 載入 BitoPro API 的金鑰、密鑰與 Email
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
EMAIL = os.getenv('EMAIL')

# API 基礎網址
BASE_URL = "https://api.bitopro.com/v3"

def get_headers(params):
    """產生 BitoPro API 驗證標頭"""

    payload = base64.urlsafe_b64encode(json.dumps(params).encode('utf-8')).decode('utf-8')
    signature = hmac.new(
        bytes(API_SECRET, 'utf-8'),
        bytes(payload, 'utf-8'),
        hashlib.sha384
    ).hexdigest()
    headers = {
        "X-BITOPRO-APIKEY": API_KEY,
        "X-BITOPRO-PAYLOAD": payload,
        "X-BITOPRO-SIGNATURE": signature,
    }
    return headers

def get_balance():
    """查詢帳戶餘額"""
    params = {"identity": EMAIL, "nonce": int(time.time() * 1000)}
    headers = get_headers(params)
    url = f"{BASE_URL}/accounts/balance"
    response = requests.get(url, headers=headers)
    return response.json()

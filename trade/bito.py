import requests
import time
import hmac
import hashlib
import base64
import json
import os
from dotenv import load_dotenv
load_dotenv()

# 你的 BitoPro API Key & Secret & Email
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
EMAIL = os.getenv('EMAIL')

# API 基礎網址
BASE_URL = "https://api.bitopro.com/v3"


def get_headers(params):
    """ 產生 BitoPro API 驗證標頭 """

    payload = base64.urlsafe_b64encode(
        json.dumps(params)
        .encode('utf-8')).decode('utf-8')

    signature = hmac.new(
        bytes(API_SECRET, 'utf-8'),
        bytes(payload, 'utf-8'),
        hashlib.sha384,
    ).hexdigest()

    headers = {
        "X-BITOPRO-APIKEY": API_KEY,
        "X-BITOPRO-PAYLOAD": payload,
        "X-BITOPRO-SIGNATURE": signature,
    }
    return headers


def get_balance():
    """ 查詢帳戶餘額 """
    params = {"identity": EMAIL, "nonce": int(time.time()) * 1000}

    headers = get_headers(params)
    url = f"{BASE_URL}/accounts/balance"

    response = requests.get(url, headers=headers)
    return response.json()


def place_order(pair, action, price, amount):
    """ 下單交易（買入或賣出） """
    params = {
        "action": action,  # "BUY" 或 "SELL"
        "amount": str(amount),  # 購買數量
        "price": str(price),  # 單價
        "timestamp": int(time.time() * 1000),
        "type": "LIMIT",  # "LIMIT" (限價) 或 "MARKET" (市價)
        "timeInForce": "POST_ONLY",
    }

    headers = get_headers(params)
    url = f"{BASE_URL}/orders/{pair}"

    response = requests.post(url, json=params, headers=headers)
    return response.json()


def get_open_orders(pair):
    """ 查詢未完成的掛單 """
    payload = {}
    headers, _ = get_headers(payload)
    url = f"{BASE_URL}/orders/{pair}"
    response = requests.get(url, headers=headers)
    return response.json()


def cancel_order(pair, order_id):
    """ 取消掛單 """
    payload = {}
    headers, _ = get_headers(payload)
    url = f"{BASE_URL}/orders/{pair}/{order_id}"
    response = requests.delete(url, headers=headers)
    return response.json()

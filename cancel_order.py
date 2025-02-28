import os
import json
import time
import hmac
import base64
import requests
import hashlib
from dotenv import load_dotenv
load_dotenv()

# 你的 BitoPro API Key & Secret & Email
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
EMAIL = os.getenv('EMAIL')
BASEURL = 'https://api.bitopro.com/v3'

def get_headers(params):
        """ 產生 BitoPro API 驗證標頭 """
        payload = base64.urlsafe_b64encode(
            json.dumps(params).encode('utf-8')).decode('utf-8')

        signature = hmac.new(
            bytes(API_SECRET, 'utf-8'),
            bytes(payload, 'utf-8'),
            hashlib.sha384,
        ).hexdigest()

        return {
            "X-BITOPRO-APIKEY": API_KEY,
            "X-BITOPRO-PAYLOAD": payload,
            "X-BITOPRO-SIGNATURE": signature,
        }

params = {
    'identity' : EMAIL,
    'nonce': int(time.time() * 1000)
}

headers = get_headers(params)

pair = 'btc_twd'
order_id = "7285681886"
endpoint = f"/orders/{pair}/{order_id}"
complete_url = BASEURL + endpoint

response = requests.delete(url=complete_url, headers=headers)
if response is not None:
    print("Cancel Order:", response.json())
else:
    print("Request failed.")

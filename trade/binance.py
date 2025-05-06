import requests
import time
import hashlib
import hmac
import os
from dotenv import load_dotenv

load_dotenv()

API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
EMAIL = os.getenv('BINANCE_EMAIL')

def get_all_pairs():
    url = 'https://api.binance.com/api/v3/exchangeInfo'
    response = requests.get(url)
    data = response.json()
    symbols = [s['symbol'] for s in data['symbols']]
    return symbols

def get_all_base_assets():
    url = 'https://api.binance.com/api/v3/exchangeInfo'
    response = requests.get(url)
    symbols = response.json().get('symbols', [])
    base_assets = {s['baseAsset'] for s in symbols if s['status'] == 'TRADING'}
    return sorted(base_assets)

def get_account_balance():
    base_url = 'https://api.binance.com'
    endpoint = '/api/v3/account'
    timestamp = int(time.time() * 1000)

    query_string = f'timestamp={timestamp}'
    signature = hmac.new(API_SECRET.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    headers = {'X-MBX-APIKEY': API_KEY}
    url = f'{base_url}{endpoint}?{query_string}&signature={signature}'

    response = requests.get(url, headers=headers)
    if response.status_code == 200:
        balances = response.json().get('balances', [])
        result = []
        for asset in balances:
            if float(asset['free']) > 0 or float(asset['locked']) > 0:
                result.append(asset)
        return result
    else:
        return ({'status':'error', 'message': response.text})
    

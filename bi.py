import requests
import time
import hashlib
import hmac
import os
from decimal import Decimal
from dotenv import load_dotenv

load_dotenv()

# 載入 BitoPro API 的金鑰、密鑰與 Email
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
EMAIL = os.getenv('BINANCE_EMAIL')
BASE_URL = "https://api.binance.com/api/v3"

def get_all_symbols():
    url = 'https://api.binance.com/api/v3/exchangeInfo'
    response = requests.get(url)
    data = response.json()
    symbols = [s['symbol'] for s in data['symbols']]
    print("所有交易對：", symbols)  # 只列前10個作為範例
    return symbols

def get_account_balance():
    base_url = 'https://api.binance.com'
    endpoint = '/api/v3/account'
    timestamp = int(time.time() * 1000)

    query_string = f'timestamp={timestamp}'
    signature = hmac.new(API_SECRET.encode(), query_string.encode(), hashlib.sha256).hexdigest()
    headers = {'X-MBX-APIKEY': API_KEY}
    url = f'{base_url}{endpoint}?{query_string}&signature={signature}'

    response = requests.get(url, headers=headers)
    print(response.json())
    if response.status_code == 200:
        balances = response.json().get('balances', [])
        for asset in balances:
            if float(asset['free']) > 0 or float(asset['locked']) > 0:
                print(f"{asset['asset']}: free: {asset['free']}, locked: {asset['locked']}")
    else:
        print("錯誤：", response.text)

def get_fee_info_from_trades(order_id, symbol):
    """查詢 Binance 訂單的總手續費與幣別"""
    fee = Decimal(0)
    fee_symbol = None

    try:
        timestamp = int(time.time() * 1000)
        query_string = f"symbol={symbol}&orderId={order_id}&timestamp={timestamp}"
        signature = hmac.new(
            API_SECRET.encode('utf-8'),
            query_string.encode('utf-8'),
            hashlib.sha256
        ).hexdigest()
        headers = {
            'X-MBX-APIKEY': API_KEY
        }

        url = f"{BASE_URL}/myTrades?{query_string}&signature={signature}"
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            trades = response.json()
            print(trades)
            for t in trades:
                fee += Decimal(t.get('commission', 0))
                fee_symbol = t.get('commissionAsset')
        else:
            print(f"查詢手續費失敗，狀態碼: {response.status_code}")
            print(f"回應內容: {response.text}")
    except Exception as e:
        print(f"取得手續費錯誤: {e}")

    return fee, fee_symbol

def get_all_base_assets_from_exchange_info():
    url = 'https://api.binance.com/api/v3/exchangeInfo'
    response = requests.get(url)
    symbols = response.json().get('symbols', [])
    base_assets = {s['baseAsset'] for s in symbols if s['status'] == 'TRADING'}
    return sorted(base_assets)



if __name__ == '__main__':
    # get_fee_info_from_trades(29216247214, 'ETHUSDT')
    print(get_all_base_assets_from_exchange_info())
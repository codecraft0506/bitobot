import os
import json
import time
import hmac
import requests
import hashlib
import base64
import threading
import websocket
from datetime import datetime
from dotenv import load_dotenv
from django.http import JsonResponse

load_dotenv()

# BitoPro API Key & Secret & Email
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
EMAIL = os.getenv('EMAIL')

# API 基礎網址
BASE_URL = "https://api.bitopro.com/v3"


class TradeWSManager:
    def __init__(self):
        self.pair = None
        self.order_size = None
        self.price_increase_percentage = None
        self.price_decrease_percentage = None
        self.last_recorded_price = None
        self.start_time = None
        self.ws = None
        self.thread = None
        self.sell_order_id = None  # 多單 ID
        self.buy_order_id = None  # 空單 ID

    def on_message(self, ws, message):
        """ 監聽 WebSocket 訂單狀態變化 """
        response = json.loads(message)
        print(f"📊 訂單更新: {response}")

        if ('event' in response and response['event'] == 'ACTIVE_ORDERS' and
            'data' in response and self.pair in response['data']):

            orders = response['data'][self.pair]
            for order in orders:
                print(order)
                if 'status' in order and order['status'] == 'FILLED':
                    if 'id' in order and order['id'] == self.sell_order_id:
                        print("賣單成交，關閉買單並重新開兩單")
                        self.cancel_order(self.buy_order_id)
                    elif 'id' in order and order['id'] == self.buy_order_id:
                        print('買單成交，關閉賣單並重新開兩單')
                        self.cancel_order(self.sell_order_id)

                    self.place_initial_orders()
                    break

    def on_error(self, ws, error):
        print(f"❌ WebSocket 錯誤: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print("🔴 WebSocket 連線關閉")

    def on_open(self, ws):
        print('✅ WebSocket 連線成功，監聽訂單狀態中...')
        # 建立第一組多單 & 空單
        self.place_initial_orders()

    def start(self, pair, order_size, price_increase_percentage, price_decrease_percentage):
        """ 啟動 WebSocket 並建立初始訂單 """
        self.pair = pair
        self.order_size = order_size
        self.price_increase_percentage = price_increase_percentage
        self.price_decrease_percentage = price_decrease_percentage
        self.start_time = datetime.now().isoformat(timespec='seconds') + "Z"

        print("⏳ 嘗試連線中...")
        self.ws_url = f"wss://stream.bitopro.com:443/ws/v1/pub/auth/orders"
        params = {
            'identity' : EMAIL,
            'nonce' : int(time.time() * 1000)
        }

        self.ws = websocket.WebSocketApp(self.ws_url,
                                         header=self.get_headers(params),
                                         on_open=self.on_open,
                                         on_message=self.on_message,
                                         on_error=self.on_error,
                                         on_close=self.on_close)

        self.thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        self.thread.start()

        try:
            while True:
                time.sleep(1)
        except KeyboardInterrupt:
            self.stop()

    def get_headers(self, params):
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

    def get_current_price(self):
        """ 取得當前市場價格 """
        url = f"{BASE_URL}/tickers/{self.pair}"
        response = requests.get(url)
        data = response.json()
        return float(data["data"]["lastPrice"])

    def place_order(self, action, price):
        """ 下限價單 """
        params = {
            "action": action,  # "BUY" 或 "SELL"
            "amount": str(self.order_size),
            "price": str(int(price)),
            "type": "LIMIT",
            "timestamp": int(time.time() * 1000)
        }

        headers = self.get_headers(params)
        url = f"{BASE_URL}/orders/{self.pair}"
        response = requests.post(url, json=params, headers=headers)

        if response.status_code == 200:
            order_id = response.json().get("orderId")
            print(f"✅ {action} 限價單建立成功: 價格 {price}, 訂單 ID: {order_id}")
            return order_id
        else:
            print(f"❌ 下單失敗: {response.json()}")
            return None

    def place_initial_orders(self):
        """ 依據當前價格建立多單和空單 """
        current_price = self.get_current_price()
        print(f"📈 當前價格: {current_price}") 

        # 賣單（SELL）
        sell_price = current_price * (1 + self.price_increase_percentage)
        self.sell_order_id = self.place_order("SELL", sell_price)

        # 買單（BUY）
        buy_price = current_price * (1 - self.price_decrease_percentage)
        self.buy_order_id = self.place_order("BUY", buy_price)

    def cancel_order(self, order_id):
        """ 取消掛單 """
        if order_id is None:
            return

        params = {"identity": EMAIL, "nonce": int(time.time() * 1000)}
        headers = self.get_headers(params)
        url = f"{BASE_URL}/orders/{self.pair}/{order_id}"

        response = requests.delete(url, headers=headers)
        if response.status_code == 200:
            print(f"✅ 訂單 {order_id} 取消成功")
        else:
            print(f"❌ 訂單取消失敗: {response.json()}")

    def stop(self):
        """ 停止 WebSocket 並取消掛單 """
        print("⏳ 停止交易機器人中...")
        self.cancel_order(self.sell_order_id)
        self.cancel_order(self.buy_order_id)

        self.ws.close()
        self.thread.join()
        print("🔴 機器人已停止")


# 啟動交易機器人（BTC/TWD，每單 0.0001 BTC，上漲 0.1% 賣出，下跌 0.1% 買入）
wsm = TradeWSManager()
wsm.start('btc_twd', 0.0001, 0.1, 0.1)

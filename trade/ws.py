import os
import json
import time
import hmac
import requests
import hashlib
import base64
import threading
import websocket
import ssl
from datetime import datetime
from dotenv import load_dotenv
from django.contrib.auth.models import User
from .models import OrderHistory

load_dotenv()

# 載入 BitoPro API 的金鑰、密鑰與 Email
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
EMAIL = os.getenv('EMAIL')

# API 基礎網址
BASE_URL = "https://api.bitopro.com/v3"

class TradeWSManager:
    _instance = None
    _initialized = False

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super(TradeWSManager, cls).__new__(cls)
        return cls._instance

    def __init__(self):
        if not self._initialized:
            self.error_message = []  # 儲存錯誤訊息列表
            self.pair = None
            self.order_size = None
            self.is_running = False
            self.price_increase_percentage = None
            self.price_decrease_percentage = None
            self.start_time = None
            self.ws = None
            self.thread = None
            self.sell_order_id = None  # 賣單 ID
            self.buy_order_id = None   # 買單 ID
            self.user = None 
            self.log_messages = []
            # 新增：用來判斷 WS 是否連線成功
            self.connected_event = threading.Event()
            self._initialized = True
            print('WSM 初始化成功')

    def log_print(self, message):
        self.log_messages.append(message)

    def log(self):
        # 回傳 JSON 格式字串，方便前端解析
        while True:
            if self.log_messages:
                yield json.dumps(self.log_messages.pop(0)) + "\n"
            time.sleep(1)

    def on_message(self, ws, message):
        """監聽 WebSocket 訂單狀態變化"""
        response = json.loads(message)
        print("📊 訂單更新:")

        if ('event' in response and response['event'] == 'ACTIVE_ORDERS' and
            'data' in response and self.pair in response['data']):
            orders = response['data'][self.pair]
            for order in orders:
                print(order)
                if order.get('status') == 0:
                    print('訂單交易中')
                if order.get('status') == 1:
                    self.create_order_history(
                        id=order.get('id'),
                        timestamp=order.get('updatedTimestamp'),
                        price=order.get('avgExecutionPrice'),
                        order_type=order.get('action'), 
                        quantity=order.get('executedAmount')
                    )
                if order.get('status') == 2:
                    if order.get('id') == self.sell_order_id:
                        print("賣單完全成交，取消買單並重新下單")
                        self.create_order_history(
                            id=order.get('id'),
                            timestamp=order.get('updatedTimestamp'),
                            price=order.get('avgExecutionPrice'),
                            order_type=order.get('action'), 
                            quantity=order.get('executedAmount')
                        )
                        self.cancel_order(self.buy_order_id)
                    elif order.get('id') == self.buy_order_id:
                        print("買單完全成交，取消賣單並重新下單")
                        self.create_order_history(
                            id=order.get('id'),
                            timestamp=order.get('updatedTimestamp'),
                            price=order.get('avgExecutionPrice'),
                            order_type=order.get('action'),
                            quantity=order.get('executedAmount')
                        )
                        self.cancel_order(self.sell_order_id)
                    self.place_initial_orders()
                    break

    def create_order_history(self, id, timestamp, price, order_type, quantity):
        # 檢查 self.user 是否已經是 User 物件
        if isinstance(self.user, User):
            user_obj = self.user
        else:
            # 假設 self.user 為使用者 ID
            user_obj = User.objects.get(id=self.user)

        # 將 timestamp 轉換為 datetime 物件
        ts = None
        if isinstance(timestamp, (int, float)):
            # 假設 timestamp 為毫秒數
            ts = datetime.fromtimestamp(timestamp / 1000)
        elif isinstance(timestamp, str):
            try:
                # 嘗試解析 ISO 格式字串（剝除尾端的 "Z"）
                ts = datetime.fromisoformat(timestamp.rstrip("Z"))
            except Exception:
                ts = datetime.now()
        else:
            ts = datetime.now()

        OrderHistory.objects.update_or_create(
            order_id=id,  # 使用 order_id 作為查找依據
            defaults={
                "user": user_obj,
                "timestamp": ts,
                "symbol": self.pair,
                "price": price,
                "order_type": order_type,
                "quantity": quantity
            }
        )

    def on_error(self, ws, error):
        self.error_message.append(f"WebSocket 錯誤: {error}")
        print(f"❌ WebSocket 錯誤: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print("🔴 WebSocket 連線關閉")

    def on_open(self, ws):
        print("✅ WebSocket 連線成功，開始監聽訂單狀態")
        self.connected_event.set()  # 標記 WS 連線成功
        self.place_initial_orders()
        # 檢查初始掛單狀態：若買賣單皆失敗，回傳錯誤訊息並停止機器人
        if not self.sell_order_id and not self.buy_order_id:
            error_msg = "初始掛單全部失敗，請檢查 API 金鑰或網路連線"
            self.error_message.append(error_msg)
            print(f"❌ {error_msg}")
            self.stop()

    def start(self, pair, order_size, price_increase_percentage, price_decrease_percentage, user):
        if self.is_running:
            return "機器人運作中"

        self.error_message = []
        self.pair = pair
        self.order_size = order_size
        self.price_increase_percentage = price_increase_percentage
        self.price_decrease_percentage = price_decrease_percentage
        self.start_time = datetime.now().isoformat(timespec='seconds') + "Z"
        self.user = user

        print("⏳ 嘗試連線中...")
        self.ws_url = "wss://stream.bitopro.com:443/ws/v1/pub/auth/orders"
        params = {
            'identity': EMAIL,
            'nonce': int(time.time() * 1000)
        }

        self.ws = websocket.WebSocketApp(
            self.ws_url,
            header=self.get_headers(params),
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=self.on_close,
            sslopt={"cert_reqs": ssl.CERT_NONE}
        )
        self.thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        self.is_running = True
        self.thread.start()
        
        # 等待 WS 連線，超過 5 秒則認定連線失敗
        if not self.connected_event.wait(timeout=5):
            self.error_message.append("WS 連線超時")
            print("❌ WS 連線超時")
            self.stop()
            return "\n".join(self.error_message)

        # 若在連線後已經有錯誤訊息，則直接回傳
        if self.error_message:
            self.stop()
            return "\n".join(self.error_message)

        return 0

    def update(self, order_size, price_increase_percentage, price_decrease_percentage):
        self.error_message = []
        self.cancel_all_orders()
        self.order_size = order_size
        self.price_increase_percentage = price_increase_percentage
        self.price_decrease_percentage = price_decrease_percentage
        self.start_time = datetime.now().isoformat(timespec='seconds') + "Z"
        self.place_initial_orders()
        return "\n".join(self.error_message) if self.error_message else 0

    def get_manager_state(self):
        """回傳目前交易機器人狀態資料（字典格式）"""
        return {
            "pair": self.pair,
            "order_size": self.order_size,
            "price_up_percentage": self.price_increase_percentage * 100,
            "price_down_percentage": self.price_decrease_percentage * 100,
            "start_time": self.start_time
        }

    def get_headers(self, params):
        """產生 BitoPro API 驗證標頭"""
        payload = base64.urlsafe_b64encode(json.dumps(params).encode('utf-8')).decode('utf-8')
        signature = hmac.new(
            bytes(API_SECRET, 'utf-8'),
            bytes(payload, 'utf-8'),
            hashlib.sha384
        ).hexdigest()
        return {
            "X-BITOPRO-APIKEY": API_KEY,
            "X-BITOPRO-PAYLOAD": payload,
            "X-BITOPRO-SIGNATURE": signature,
        }

    def get_current_price(self):
        """取得當前市場價格"""
        url = f"{BASE_URL}/tickers/{self.pair}"
        response = requests.get(url)
        data = response.json()
        return float(data["data"]["lastPrice"])

    def place_order(self, action, price):
        """下限價單"""
        params = {
            "action": action,  # "BUY" 或 "SELL"
            "amount": str(self.order_size),
            "price": str(round(price, 8)),
            "type": "LIMIT",
            "timestamp": int(time.time() * 1000)
        }
        headers = self.get_headers(params)
        url = f"{BASE_URL}/orders/{self.pair}"
        response = requests.post(url, json=params, headers=headers)
        if response.status_code == 200:
            order_id = response.json().get("orderId")
            print(f"✅ {action} 限價單建立成功: 價格 {str(round(price, 8))}, 訂單 ID: {order_id}")
            self.log_print({'status': True, 'message': f'{action} 限價單建立成功: 價格 {str(round(price, 8))}, 訂單 ID: {order_id}'})
            return order_id
        else:
            error_info = response.json()
            print(f"❌ 下單失敗: {error_info}")
            self.error_message.append(f"下單失敗: {error_info}")
            self.log_print({'status': False, 'message': f'{action} 限價單建立失敗: {error_info}'})
            return None

    def place_initial_orders(self):
        """根據當前價格建立買單和賣單"""
        current_price = self.get_current_price()
        print(f"📈 當前價格: {current_price}")
        # 賣單（SELL）
        sell_price = current_price * (1 + self.price_increase_percentage)
        self.sell_order_id = self.place_order("SELL", sell_price)
        # 買單（BUY）
        buy_price = current_price * (1 - self.price_decrease_percentage)
        self.buy_order_id = self.place_order("BUY", buy_price)

    def cancel_all_orders(self):
        self.cancel_order(self.buy_order_id)
        self.cancel_order(self.sell_order_id)

    def cancel_order(self, order_id):
        """取消掛單"""
        if order_id is None:
            return

        params = {"identity": EMAIL, "nonce": int(time.time() * 1000)}
        headers = self.get_headers(params)
        url = f"{BASE_URL}/orders/{self.pair}/{order_id}"
        response = requests.delete(url, headers=headers)
        if response.status_code == 200:
            print(f"✅ 訂單 {order_id} 取消成功")
        else:
            error_info = response.json()
            self.error_message.append(f"訂單 {order_id} 取消失敗: {error_info}")
            print(f"❌ 訂單取消失敗: {error_info}")

    def stop(self):
        """停止 WebSocket 並取消所有掛單"""
        print("⏳ 停止交易機器人中...")
        self.error_message = []
        self.cancel_all_orders()
        if self.ws:
            self.ws.close()
        if self.thread:
            self.thread.join(timeout=5)
        self.is_running = False
        print("🔴 機器人已停止")
        return "\n".join(self.error_message) if self.error_message else 0

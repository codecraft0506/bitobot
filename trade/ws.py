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
from decimal import Decimal
from datetime import datetime
from dotenv import load_dotenv
from .models import Trade

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
            self.precision = None
            self.log_messages = []
            # 用來判斷 WS 是否連線成功
            self.connected_event = threading.Event()
            self.manual_close = False
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
        if self.canceling : return
        response = json.loads(message)
        print("📊 訂單更新:")

        if ('data' in response and 'orderID' in response['data']):
            order_data = self.get_order_data(response['data']['orderID'])
            self.save_order(order_data)
            print(order_data)

            if order_data.get('status') == 0:
                print('訂單交易中')
            if order_data.get('status') == 2:
                if order_data.get('id') == self.sell_order_id:
                    print("賣單完全成交，取消買單並重新下單")
                elif order_data.get('id') == self.buy_order_id:
                    print("買單完全成交，取消賣單並重新下單")
                self.cancel_all_orders()
                self.place_initial_orders()

    def on_error(self, ws, error):
        err_msg = f"WebSocket 錯誤: {error}"
        self.error_message.append(err_msg)
        print(f"❌ {err_msg}")

    def on_close(self, ws, close_status_code, close_msg, attempt = 0):
        print("🔴 WebSocket 連線關閉")

        if self.manual_close:
            print("🛑 手動關閉 WebSocket，不啟動重連")
            return 
        
        if attempt > 3:
            error_msg = "WebSocket 連線失敗，超過最大嘗試次數，機器人停止"
            self.error_message.append(error_msg)
            print(f"❌ {error_msg}")
            self.stop()
            return
        
        print(f"⚠️ WebSocket 斷線，嘗試重新連線 (第 {attempt} 次)...")
        self.reconnect(attempt + 1) 

    def on_open(self, ws):
        print("✅ WebSocket 連線成功，開始監聽訂單狀態")
        self.connected_event.set()  # 標記 WS 連線成功
        self.place_initial_orders()
        if not self.sell_order_id and not self.buy_order_id:
            error_msg = "初始掛單全部失敗，請檢查 API 金鑰或網路連線"
            self.error_message.append(error_msg)
            print(f"❌ {error_msg}")
            self.stop()
        self.wait_start = True
        
    def start(self, pair, order_size, price_increase_percentage, price_decrease_percentage, user):
        if self.is_running:
            return "機器人運作中"
        
        url = 'https://api.bitopro.com/v3/provisioning/trading-pairs'
        response = requests.get(url)
        datas = response.json()['data']
        for data in datas:
            if data.get('pair') == pair:
                self.precision = int(data.get('quotePrecision'))

        self.error_message = []  # 清空錯誤訊息列表
        self.pair = pair
        self.order_size = order_size
        self.price_increase_percentage = price_increase_percentage
        self.price_decrease_percentage = price_decrease_percentage
        self.start_time = datetime.now().isoformat(timespec='seconds') + "Z"
        self.wait_start = False
        self.canceling = False
        self.manual_close = False
        self.user = user

        print("⏳ 嘗試連線中...")
        self.ws_url = "wss://stream.bitopro.com:443/ws/v1/pub/auth/user-trades"
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
            on_close=self.on_close
        )
        self.thread = threading.Thread(
            target=lambda: self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}),
            daemon=True
        )
        self.is_running = True
        self.thread.start()

        # 等待 WS 連線，超時則返回錯誤
        if not self.connected_event.wait(timeout=5):
            self.error_message.append("WS 連線超時")
            print("❌ WS 連線超時")
            self.stop()
            return "\n".join(self.error_message)

        while (not self.wait_start):
            time.sleep(1)

        # 如果有錯誤訊息，返回它們
        if self.error_message:
            return "\n".join(self.error_message)

        return 0  # 成功時返回 0

    def update(self, order_size, price_increase_percentage, price_decrease_percentage):
        if not self.is_running:
            return '機器人未運行'
        self.error_message = []  # 清空錯誤訊息列表
        self.cancel_all_orders()
        self.order_size = order_size
        self.price_increase_percentage = price_increase_percentage
        self.price_decrease_percentage = price_decrease_percentage
        self.start_time = datetime.now().isoformat(timespec='seconds') + "Z"
        self.place_initial_orders()
        return "\n".join(self.error_message) if self.error_message else 0

    def stop(self):
        if not self.is_running:
            return '機器人未運行'
        print("⏳ 停止交易機器人中...")
        self.error_message = [] # 清空錯誤訊息列表
        self.manual_close = True
        self.cancel_all_orders()
        if self.ws:
            self.ws.close()
        if self.thread:
            try:
                self.thread.join(timeout=5)
            except RuntimeError as e:
                self.error_message.append(f"WebSocket 錯誤: {e}")
                print(f"❌ WebSocket 錯誤: {e}")
        self.is_running = False
        print("🔴 機器人已停止")
        return "\n".join(self.error_message) if self.error_message else 0
      
    def reconnect(self, attempt):
        """嘗試重新連接 WebSocket"""
        time.sleep(5)  # 等待 5 秒後重新嘗試連線

        self.ws = websocket.WebSocketApp(
            self.ws_url,
            header=self.get_headers({
                'identity': EMAIL,
                'nonce': int(time.time() * 1000)
            }),
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=lambda ws, code, msg: self.on_close(ws, code, msg, attempt)  # 傳遞 `attempt` 次數
        )

        self.thread = threading.Thread(
            target=lambda: self.ws.run_forever(sslopt={"cert_reqs": ssl.CERT_NONE}),
            daemon=True
        )
        self.thread.start()

    def get_manager_state(self):
        return {
            "pair": self.pair,
            "order_size": self.order_size,
            "price_up_percentage": self.price_increase_percentage * 100,
            "price_down_percentage": self.price_decrease_percentage * 100,
            "start_time": self.start_time
        }
    
    def get_order_data(self, order_id):
        params = {
            'pair' : self.pair,
            'order_id': order_id,
            'nonce': int(time.time() * 1000)
        }

        headers = self.get_headers(params)

        url = f'{BASE_URL}/orders/{self.pair}/{order_id}'
        response = requests.get(url, headers=headers)
        data = response.json()
        return data
        
    def get_headers(self, params):
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
        url = f"{BASE_URL}/tickers/{self.pair}"
        response = requests.get(url)
        data = response.json()
        return float(data["data"]["lastPrice"])

    def place_order(self, action, price):
        params = {
            "action": action,
            "amount": str(self.order_size),
            "price": str(round(price, self.precision)),
            "type": "LIMIT",
            "timestamp": int(time.time() * 1000)
        }
        headers = self.get_headers(params)
        url = f"{BASE_URL}/orders/{self.pair}"
        response = requests.post(url, json=params, headers=headers)
        if response.status_code == 200:
            order_id = response.json().get("orderId")
            msg = f"✅ {action} 限價單建立成功: 價格 {str(round(price, self.precision))}, 訂單 ID: {order_id}"
            print(msg)
            self.log_print({'status': True, 'message': msg})
            return order_id
        else:
            error_info = response.json()
            error_msg = f"❌ 下單失敗: {error_info}"
            print(error_msg)
            self.error_message.append(error_msg)
            self.log_print({'status': False, 'message': f"{action} 限價單建立失敗: {error_info}"})
            return None

    def place_initial_orders(self):
        current_price = self.get_current_price()
        print(f"📈 當前價格: {current_price}")
        sell_price = current_price * (1 + self.price_increase_percentage)
        self.sell_order_id = self.place_order("SELL", sell_price)
        buy_price = current_price * (1 - self.price_decrease_percentage)
        self.buy_order_id = self.place_order("BUY", buy_price)
        if self.sell_order_id is None and self.buy_order_id is None:
            error_msg = "初始掛單全部失敗，請檢查 API 金鑰或網路連線"
            self.stop()
            self.error_message.append(error_msg)
            print(f"❌ {error_msg}")

    def cancel_all_orders(self):
        self.canceling = True
        time.sleep(1)
        params = {
            'identity' : EMAIL,
            'nonce' : int(time.time() * 1000),
        }
        
        headers = self.get_headers(params)
        url = f'{BASE_URL}/orders/all/'
        response = requests.delete(url=url, headers=headers)
        if response.status_code == 200:
            self.buy_order_id = None
            self.sell_order_id = None
            print('訂單全部取消成功')
        else:
            error_info = response.json()
            error_msg = f'訂單取消失敗 : {error_info}'
            self.error_message.append(error_msg)
            print(error_msg)
        self.canceling = False

    def cancel_order(self, order_id):
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
            error_msg = f"❌ 訂單 {order_id} 取消失敗: {error_info}"
            self.error_message.append(error_msg)
            print(error_msg)

    def save_order(self, data):
        Trade.objects.update_or_create(
            defaults={
                'user_email': EMAIL,
                'id': data.get('id'),
                'pair': data.get('pair'),
                'action': data.get('action'),
                'quantity': Decimal(data.get('executedAmount')),
                'price': Decimal(data.get('avgExecutionPrice')),
                'fee': Decimal(data.get('fee')),
                'fee_symbol': data.get('feeSymbol'),
                'trade_date': data.get('updatedTimestamp'),
                'trade_or_not' : True if int(data.get('status')) == 2 else False 
            },
            pk = data.get('id')
        )

'''
Orders: {'data': [{
'action': 'BUY',
'avgExecutionPrice': '0', 
'fee': '0', 
'feeSymbol': 'pol', 
'bitoFee': '0', 
'executedAmount': '0', 
'id': '2349437194', 
'originalAmount': '1', 
'pair': 'pol_twd', 
'price': '6.308', 
'remainingAmount': '1', 
'seq': 'POLTWD9744129620', 
'status': 0, 
'createdTimestamp': 1743782486, 
'updatedTimestamp': 1743782486, 
'total': '0', 
'type': 'LIMIT', 
'timeInForce': 'GTC'}]}
'''
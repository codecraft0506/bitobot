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
from .models import Trade,SpotTrade
from telegram import Bot
import asyncio

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
            self.sell_orders = []
            self.buy_orders = []
            self.user = None 
            self.precision = None
            self.last_price_5min_ago = None
            self.is_exceed_5min=None
            self.target_after_exceed = None
            self.price_timer = None
            self.log_messages = []
            # 用來判斷 WS 是否連線成功
            self.connected_event = threading.Event()
            self.manual_close = False
            self._initialized = True
            self.trade_count = None
            self.origin_price = None
            self.last_trade_price = None
            self.price_cancel_cv = None
            self.price_reset_cv = None
            self.history_print('WSM 初始化成功')

    def on_message(self, ws, message):
        """監聽 WebSocket 訂單狀態變化"""
        response = json.loads(message)
        self.history_print("📊 訂單更新:")

        if ('data' in response and 'orderID' in response['data']):
            order_data = self.get_order_data(response['data']['orderID'])
            self.history_print(order_data)
            self.save_order(order_data)
            if order_data.get('status') == 0:
                self.history_print('訂單交易中')
            if order_data.get('status') == 2:
                id = order_data.get('id')
                if id in self.sell_orders:
                    self.history_print("賣單成交")
                    self.place_order("BUY", self.last_trade_price)
                    self.place_order("SELL", self.last_trade_price + self.origin_price * self.price_increase_percentage * (len(self.sell_orders) + 1))
                    self.sell_orders.remove(id)
                    self.last_trade_price = float(order_data.get('price'))
                elif id in self.buy_orders:
                    self.history_print("買單成交")
                    self.place_order("BUY", self.last_trade_price - self.origin_price * self.price_decrease_percentage * (len(self.buy_orders) + 1))
                    self.place_order("SELL", self.last_trade_price)
                    self.buy_orders.remove(id)
                    self.last_trade_price = float(order_data.get('price'))

    def on_error(self, ws, error):
        err_msg = f"WebSocket 錯誤: {error}"
        self.error_message.append(err_msg)
        self.history_print(f"❌ {err_msg}")

    def on_close(self, ws, close_status_code, close_msg, attempt = 0):
        self.history_print("🔴 WebSocket 連線關閉")

        if self.manual_close:
            self.history_print("🛑 手動關閉 WebSocket，不啟動重連")
            return 
        
        if attempt > 3:
            error_msg = "WebSocket 連線失敗，超過最大嘗試次數，機器人停止"
            self.error_message.append(error_msg)
            self.history_print(f"❌ {error_msg}")
            self.stop()
            return
        
        self.history_print(f"⚠️ WebSocket 斷線，嘗試重新連線 (第 {attempt} 次)...")
        self.reconnect(attempt + 1) 

    def on_open(self, ws):
        self.history_print("✅ WebSocket 連線成功，開始監聽訂單狀態")
        self.connected_event.set()  # 標記 WS 連線成功
        self.place_initial_orders()
        self.start_price_timer()
        self.wait_start = True
        
    def start(self, pair, order_size, price_increase_percentage, price_decrease_percentage, user, trade_count, price_reset_cv, price_cancel_cv):
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
        self.manual_close = False
        self.user = user
        self.price_reset_cv = price_reset_cv
        self.price_cancel_cv = price_cancel_cv
        self.trade_count = trade_count

        self.history_print("⏳ 嘗試連線中...")
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
            self.history_print("❌ WS 連線超時")
            self.stop()
            return "\n".join(self.error_message)

        while (not self.wait_start):
            time.sleep(1)

        # 如果有錯誤訊息，返回它們
        if self.error_message:
            return "\n".join(self.error_message)

        return 0  # 成功時返回 0

    def update(self, order_size, price_increase_percentage, price_decrease_percentage, trade_count, price_reset_cv, price_cancel_cv):
        if not self.is_running:
            return '機器人未運行'
        self.error_message = []  # 清空錯誤訊息列表
        self.cancel_all_orders()
        self.order_size = order_size
        self.price_increase_percentage = price_increase_percentage
        self.price_decrease_percentage = price_decrease_percentage
        self.trade_count = trade_count
        self.price_reset_cv = price_reset_cv
        self.price_cancel_cv = price_cancel_cv
        self.start_time = datetime.now().isoformat(timespec='seconds') + "Z"
        self.place_initial_orders()
        self.start_price_timer()
        return "\n".join(self.error_message) if self.error_message else 0
    
    def unexpected_stop(self):
        self.manual_close = True
        self.cancel_all_orders()
        if self.price_timer is not None:
            self.price_timer.cancel()
            self.history_print("🛑 已停止價格更新計時器")
        if self.ws:
            self.ws.close()
        if self.thread:
            try:
                self.thread.join(timeout=5)
            except RuntimeError as e:
                self.error_message.append(f"WebSocket 錯誤: {e}")
                self.history_print(f"❌ WebSocket 錯誤: {e}")
        self.is_running = False
        self.history_print("🔴 機器人已停止")

        # 發送 Telegram 通知
        asyncio.run(self.send_telegram_notification("🔴 交易機器人已停止運行"))

        return "\n".join(self.error_message) if self.error_message else 0

    def stop(self):
        if not self.is_running:
            return '機器人未運行'
        self.history_print("⏳ 停止交易機器人中...")
        self.error_message = []  # 清空錯誤訊息列表
        self.manual_close = True
        self.cancel_all_orders()
        if self.price_timer is not None:
            self.price_timer.cancel()
            self.history_print("🛑 已停止價格更新計時器")
        if self.ws:
            self.ws.close()
        if self.thread:
            try:
                self.thread.join(timeout=5)
            except RuntimeError as e:
                self.error_message.append(f"WebSocket 錯誤: {e}")
                self.history_print(f"❌ WebSocket 錯誤: {e}")
        self.is_running = False
        self.history_print("🔴 機器人已停止")

        # 發送 Telegram 通知
        asyncio.run(self.send_telegram_notification("🔴 交易機器人已停止運行"))

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
            "start_time": self.start_time,
            "trade_count": self.trade_count,
            "price_reset_cv": self.price_reset_cv * 100,
            "price_cancel_cv" : self.price_cancel_cv * 100,
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

    def place_order(self, action, price, is_exceed=False, target_after_exceed=None):
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

            if action == 'BUY':
                self.buy_orders.append(order_id)
            elif action == 'SELL':
                self.sell_orders.append(order_id)

            msg = f"✅ {action} 限價單建立成功: 價格 {str(round(price, self.precision))}, 訂單 ID: {order_id}"
            self.history_print(msg)
            return order_id
        else:
            error_info = response.json()
            error_msg = f"下單失敗: {error_info}"
            self.history_print(error_msg)
            if error_msg not in self.error_message : self.error_message.append(error_msg)
            return None
    

    def place_initial_orders(self):
        current_price = self.get_current_price()
        self.origin_price = current_price
        self.last_trade_price = current_price

        self.history_print(f"📈 當前價格: {current_price}")

        for i in range(1, self.trade_count + 1):
            sell_price = current_price * (1 + (self.price_increase_percentage * i))
            self.place_order("SELL", sell_price)

            
        for i in range(1, self.trade_count + 1):
            buy_price = current_price * (1 - (self.price_decrease_percentage * i))
            self.place_order("BUY", buy_price)


        if (len(self.sell_orders) == 0) and (len(self.buy_orders) == 0):
            error_msg = "初始掛單全部失敗，請檢查 API 金鑰/網路/參數/餘額 等問題"
            self.unexpected_stop()
            self.error_message.append(error_msg)
            self.history_print(f"❌ {error_msg}")



    def cancel_all_orders(self):
        params = {
            'identity' : EMAIL,
            'nonce' : int(time.time() * 1000),
        }
        
        headers = self.get_headers(params)
        url = f'{BASE_URL}/orders/all/'
        response = requests.delete(url=url, headers=headers)
        if response.status_code == 200:
            self.buy_orders.clear()
            self.sell_orders.clear()
            self.history_print('訂單全部取消成功')
        else:
            error_info = response.json()
            error_msg = f'訂單取消失敗 : {error_info}'
            self.error_message.append(error_msg)
            self.history_print(error_msg)
        time.sleep(1) # API 有一秒限制 防呆用

    def cancel_order(self, order_id):
        if order_id is None:
            return

        params = {"identity": EMAIL, "nonce": int(time.time() * 1000)}
        headers = self.get_headers(params)
        url = f"{BASE_URL}/orders/{self.pair}/{order_id}"
        response = requests.delete(url, headers=headers)
        if response.status_code == 200:
            self.history_print(f"✅ 訂單 {order_id} 取消成功")
        else:
            error_info = response.json()
            error_msg = f"❌ 訂單 {order_id} 取消失敗: {error_info}"
            self.error_message.append(error_msg)
            self.history_print(error_msg)

    def save_order(self, data):
        try:
            quantity = Decimal(data.get('executedAmount'))
        except Exception as e:
            quantity = Decimal(0)
            print(f"executedAmount Decimal 轉換錯誤: {data.get('executedAmount')}")

        try:
            price = Decimal(data.get('avgExecutionPrice'))
        except Exception as e:
            price = Decimal(0)
            print(f"avgExecutionPrice Decimal 轉換錯誤: {data.get('avgExecutionPrice')}")

        try:
            fee = Decimal(data.get('fee'))
        except Exception as e:
            fee = Decimal(0)
            print(f"fee Decimal 轉換錯誤: {data.get('fee')}")



        Trade.objects.update_or_create(
            defaults={
                'user_email': EMAIL,
                'id': data.get('id'),
                'pair': data.get('pair'),
                'action': data.get('action'),
                'quantity': quantity,
                'price': price,
                'fee': fee,
                'fee_symbol': data.get('feeSymbol'),
                'trade_date': data.get('updatedTimestamp'),
                'trade_or_not' : True if int(data.get('status')) == 2 else False 
            },
            pk = data.get('id')
        )

    def start_price_timer(self):
        if self.price_timer is not None:
            self.last_price_5min_ago = None
            self.price_timer.cancel()
            self.price_timer = None
            # 如果計時已存在 則銷毀並重新計時
        
        def update_price():
            current = self.get_current_price()
            # 第一次執行時 last_price 以及手動重設時 可能是 None
            if self.last_price_5min_ago is not None:
                change_pct = abs(current - self.last_price_5min_ago) / self.last_price_5min_ago
                if (change_pct >= self.price_cancel_cv):
                    self.history_print(f"⚠️ 價格在 5 分鐘內變動超過 10%：{round(change_pct*100, 2)}%，取消掛單")
                    self.stop()
                    return
                elif (change_pct >= self.price_reset_cv):
                    self.history_print(f"⚠️ 價格在 5 分鐘內變動超過 5%：{round(change_pct*100, 2)}%，重新掛單")
                    # 取消掛單
                    self.cancel_all_orders()
                    # 重新掛單
                    self.place_initial_orders()
                else:
                    self.history_print(f"✅ 價格變動在正常範圍內（{round(change_pct*100, 2)}%）")
            self.last_price_5min_ago = current
            self.history_print(f"⏱️ 更新 5 分鐘前價格為：{self.last_price_5min_ago}")

            # 每 5 分鐘再次更新
            self.price_timer = threading.Timer(300, update_price)
            self.price_timer.start()

        update_price()

    async def send_telegram_notification(self, message):
        """發送 Telegram 通知 (適配 22.0 版本)"""
        bot_token = os.getenv('TELEGRAM_BOT_TOKEN')
        chat_id = os.getenv('TELEGRAM_CHAT_ID')

        if not bot_token or not chat_id:
            self.history_print("❌ Telegram 配置缺失，無法發送通知")
            return

        try:
            bot = Bot(token=bot_token)
            await bot.send_message(chat_id=chat_id, text=message)
            self.history_print(f"✅ 已發送 Telegram 通知: {message}")
        except Exception as e:
            self.history_print(f"❌ 發送 Telegram 通知失敗: {e}")

    def history_print(self, txt):
        print(txt)
        with open("debug.txt", "a", encoding="utf-8") as f:
            f.write(f'{datetime.fromtimestamp(time.time())} : {txt}\n')

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
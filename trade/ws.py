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
import math
from decimal import Decimal, ROUND_CEILING
from datetime import datetime
from dotenv import load_dotenv
from .models import Trade
from telegram import Bot
import asyncio

load_dotenv()

# 載入 BitoPro API 的金鑰、密鑰與 Email
API_KEY = os.getenv('BINANCE_API_KEY')
API_SECRET = os.getenv('BINANCE_API_SECRET')
EMAIL = os.getenv('BINANCE_EMAIL')

# API 基礎網址
BASE_URL = "https://api.binance.com/api/v3"

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

        if 'e' in response and response['e'] == 'executionReport':
            order_id = response.get('i')
            order_data = self.get_order_data(order_id)

            #  檢查訂單資料是否取得成功
            if not order_data: 
                self.history_print(f"無法取得訂單資料 (ID: {order_id}），略過處理")  
                return  
            
            self.history_print("==訂單更新==")
            self.history_print(order_data)
            if order_data.get('status') == 'NEW':
                self.history_print('新建訂單')
                return
            
            if order_data.get('status') == "CANCELED":
                self.history_print('取消訂單')
                return

            self.save_order(order_data)

            

            if order_data.get('status') == 'FILLED':
                order_id = order_data.get('orderId')
                if order_id in self.sell_orders:
                    self.history_print("==賣單成交==")
                    self.place_order("BUY", self.last_trade_price)
                    self.place_order("SELL", self.last_trade_price + self.origin_price * self.price_increase_percentage * (len(self.sell_orders) + 1))
                    self.sell_orders.remove(order_id)
                    self.last_trade_price = float(order_data.get('price'))
                elif order_id in self.buy_orders:
                    self.history_print("==買單成交==")
                    self.place_order("BUY", self.last_trade_price - self.origin_price * self.price_decrease_percentage * (len(self.buy_orders) + 1))
                    self.place_order("SELL", self.last_trade_price)
                    self.buy_orders.remove(order_id)
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
        
        url = 'https://api.binance.com/api/v3/exchangeInfo'
        try:
            response = requests.get(url)
            symbol_info = next(
                (s for s in response.json()['symbols'] if s['symbol'] == pair),
                None
            )
            if symbol_info is None:
                self.error_message.append(f"找不到交易對資訊: {pair}")
                return "\n".join(self.error_message)
            # 設定價格精度（price tick size）
            for f in symbol_info["filters"]:
                if  f["filterType"] == "PRICE_FILTER":
                    self.precision = int(round(-1 * math.log10(float(f["tickSize"]))))
                    self.tickSize = float(f['tickSize'])
                elif f["filterType"] == "LOT_SIZE":
                    self.min_qty_precision = int(round(-1 * math.log10(float(f["minQty"]))))  # 最小下單精度
                elif f["filterType"] == "NOTIONAL":
                    self.min_notional = float(f["minNotional"])  # 最小下單金額

        except Exception as e:
            self.error_message.append(f"取得交易對精度失敗: {e}")
            return "\n".join(self.error_message)

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

        self.history_print("嘗試建立 WebSocket 連線中...")

        listen_key_resp = requests.post(
            'https://api.binance.com/api/v3/userDataStream',
            headers={'X-MBX-APIKEY': API_KEY}
        )

        if listen_key_resp.status_code != 200:
            self.error_message.append("無法取得 listenKey")
            return "\n".join(self.error_message)
        
        self.listen_key = listen_key_resp.json()['listenKey']
        self.ws_url = f"wss://stream.binance.com:9443/ws/{self.listen_key}"

        self.ws = websocket.WebSocketApp(
            self.ws_url,
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
        self.start_listenkey_keepalive()

        # 等待 WS 連線，超時則返回錯誤
        if not self.connected_event.wait(timeout=5):
            self.error_message.append("WS 連線超時")
            self.history_print("WS 連線超時")
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
        """嘗試重新連接 Binance WebSocket"""
        time.sleep(5)  # 等待 5 秒後重新嘗試連線

        self.ws = websocket.WebSocketApp(
            self.ws_url,
            on_open=self.on_open,
            on_message=self.on_message,
            on_error=self.on_error,
            on_close=lambda ws, code, msg: self.on_close(ws, code, msg, attempt)  # 傳遞 attempt 次數
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
        """使用 Binance API 查詢單筆訂單資訊"""
        timestamp = int(time.time() * 1000)
        query_string = f"symbol={self.pair}&orderId={order_id}&timestamp={timestamp}"
        signature = hmac.new(
            bytes(API_SECRET, 'utf-8'),
            bytes(query_string, 'utf-8'),
            hashlib.sha256
        ).hexdigest()

        url = f"{BASE_URL}/order?{query_string}&signature={signature}"
        headers = {"X-MBX-APIKEY": API_KEY}
        response = requests.get(url, headers=headers)

        try:
            data = response.json()
            if response.status_code == 200 and "orderId" in data:
                return data
            else:
                self.history_print(f"❌ 查詢訂單失敗: {data}")
                return {}
        except Exception as e:
            self.history_print(f"❌ get_order_data 發生錯誤: {e}")
            return {}

    def get_current_price(self):
        url = f"{BASE_URL}/ticker/price?symbol={self.pair}"
        response = requests.get(url)
        data = response.json()
        return float(data["price"])

    def place_order(self, action, price, is_exceed=False, target_after_exceed=None):
        url = f"{BASE_URL}/order"
        
        params = {
            "symbol": self.pair,
            "side": action.upper(),
            "type": "LIMIT",
            "timeInForce": "GTC",
            "quantity": str(self.order_size),
            "price": str(round(price, self.precision)),
            "timestamp": int(time.time() * 1000)
        }

        query_string = "&".join([f"{k}={v}" for k, v in params.items()])
        signature = hmac.new(
            API_SECRET.encode("utf-8"),
            query_string.encode("utf-8"),
            hashlib.sha256).hexdigest()
        
        headers = {
        "X-MBX-APIKEY": API_KEY
        }
    
        response = requests.post(
            url + "?" + query_string + f"&signature={signature}",
            headers=headers
        )
    
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
            self.history_print(error_info)
            if error_info['msg'] == 'Filter failure: NOTIONAL':
                value = Decimal(str(self.min_notional)) / Decimal(str(self.get_current_price()))
                min_qty_required = value.quantize(Decimal(f'1e-{self.min_qty_precision}'), rounding=ROUND_CEILING)
                error_info = f'最小下單數量: {min_qty_required}'
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
        timestamp = int(time.time() * 1000)
        query_string = f"symbol={self.pair}&timestamp={timestamp}"
        signature = hmac.new(
            bytes(API_SECRET, 'utf-8'),
            bytes(query_string, 'utf-8'),
            hashlib.sha256
        ).hexdigest()

        url = f'{BASE_URL}/openOrders?symbol={self.pair}&timestamp={timestamp}&signature={signature}'

        headers = {"X-MBX-APIKEY": API_KEY}
        response = requests.get(url, headers=headers)

        if response.status_code == 200:
            open_orders = response.json()
            for order in open_orders:
                order_id = order.get("orderId")
                cancel_query = f"symbol={self.pair}&orderId={order_id}&timestamp={int(time.time() * 1000)}"
                cancel_signature = hmac.new(
                    bytes(API_SECRET, 'utf-8'),
                    bytes(cancel_query, 'utf-8'),
                    hashlib.sha256
                ).hexdigest()

                cancel_url = f"https://api.binance.com/api/v3/order?{cancel_query}&signature={cancel_signature}"
                cancel_response = requests.delete(cancel_url, headers=headers)
                if cancel_response.status_code == 200:
                    self.history_print(f"✅ 成功取消訂單 {order_id}")
                else:
                    self.history_print(f"❌ 取消訂單 {order_id} 失敗: {cancel_response.text}")
                    self.error_message.append(f"取消訂單 {order_id} 失敗")

            self.buy_orders.clear()
            self.sell_orders.clear()
            self.history_print('訂單全部取消成功')
        else:
            error_msg = f"❌ 無法取得掛單列表: {response.text}"
            self.error_message.append(error_msg)
            self.history_print(error_msg)

    def cancel_order(self, order_id):
        if order_id is None:
            return

        timestamp = int(time.time() * 1000)
        query_string = f"symbol={self.pair}&orderId={order_id}&timestamp={timestamp}"
        signature = hmac.new(
            bytes(API_SECRET, 'utf-8'),
            bytes(query_string, 'utf-8'),
            hashlib.sha256
        ).hexdigest()

        url = f"https://api.binance.com/api/v3/order?{query_string}&signature={signature}"
        headers = {"X-MBX-APIKEY": API_KEY}
        response = requests.delete(url, headers=headers)

        try:
            res_data = response.json()
        except Exception:
            res_data = {}
    
        if response.status_code == 200 and not res_data.get("code"):
            self.history_print(f"✅ 訂單 {order_id} 取消成功")
        else:
            error_msg = f"❌ 訂單 {order_id} 取消失敗: {res_data}"
            self.error_message.append(error_msg)
            self.history_print(error_msg)

    def save_order(self, data):
        order_id = data.get('orderId')
        symbol = data.get('symbol')

        fee, fee_symbol = self.get_fee_info_from_trades(order_id, symbol)

        Trade.objects.update_or_create(
            defaults={
                'user_email': EMAIL,
                'id': order_id,
                'pair': symbol,
                'action': data.get('side'),
                'quantity': Decimal(data.get('executedQty', 0)),
                'price': Decimal(data.get('price', 0)),
                'fee': fee,
                'fee_symbol': fee_symbol,  # Binance 不回 feeSymbol，需要查成交明細才有
                'trade_date': data.get('updateTime') or data.get('transactTime'),
                'trade_or_not': True if data.get('status') == 'FILLED' else False
            },
            pk=data.get('orderId')
        )

    def get_fee_info_from_trades(self, order_id, symbol):
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
                for t in trades:
                    fee += Decimal(t.get('commission', 0))
                    fee_symbol = t.get('commissionAsset')
            else:
                self.history_print(f"查詢手續費失敗")
        except Exception as e:
            self.history_print(f"取得手續費錯誤: {e}")

        return fee, fee_symbol


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

    def start_listenkey_keepalive(self):
        def keep_alive():
            while self.is_running:
                time.sleep(30 * 60)  # 每 30 分鐘
                requests.put(
                    'https://api.binance.com/api/v3/userDataStream',
                    params={'listenKey': self.listen_key},
                    headers={'X-MBX-APIKEY': API_KEY}
                )
                self.history_print("listenKey 已自動續約")

        self.listen_key_thread = threading.Thread(target=keep_alive, daemon=True)
        self.listen_key_thread.start()
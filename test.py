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

# 你的 BitoPro API Key & Secret & Email
API_KEY = os.getenv('API_KEY')
API_SECRET = os.getenv('API_SECRET')
EMAIL = os.getenv('EMAIL')

# API 基礎網址
BASE_URL = "https://api.bitopro.com/v3"

class trade_ws_manager:
    def on_message(self, ws, message):
        # 接收到的 ticker 資訊
        data = json.loads(message)
        last_price = float(data['lastPrice'])
        if self.last_recorded_price == None : self.last_recorded_price = last_price
        
        # 漲跌幅
        change_rate = (last_price - self.last_recorded_price) / self.last_recorded_price
        print(f"交易對: {data['pair']}, 最新價格: {data['lastPrice']}, 紀錄價格: {self.last_recorded_price}, 相對漲跌幅: {change_rate:.7f}")

        if ((change_rate >= 0) and (change_rate >= self.price_increase_percentage)):
            self.place_order("SELL")
        elif ((change_rate <= 0) and (change_rate <= -self.price_decrease_percentage)):
            self.place_order("BUY")
        else:
            print('波動')

    def on_error(self, ws, error):
        print(f"發生錯誤: {error}")

    def on_close(self, ws, close_status_code, close_msg):
        print("WebSocket 連線關閉")

    def on_open(self, ws):
        print('WebSocket 連線成功，按下 Ctrl + C 中斷')

    def start(self, pair, order_size, price_increase_percentage, price_decrease_percentage):

        # 紀錄交易資訊
        self.ws_url = f"wss://stream.bitopro.com:443/ws/v1/pub/tickers/{pair}"
        self.pair = pair
        self.order_size = order_size
        self.price_increase_percentage = price_increase_percentage
        self.price_decrease_percentage = price_decrease_percentage
        self.last_recorded_price = None
        self.start_time = datetime.now().isoformat(timespec='seconds') + "Z"
        print(self.start_time)
        print(API_KEY)
        print(API_SECRET)
        print(EMAIL)

        self.ws = websocket.WebSocketApp(self.ws_url,
                                    on_open=self.on_open,
                                    on_message=self.on_message,
                                    on_error=self.on_error,
                                    on_close=self.on_close)
        
        print('嘗試連線中...')
        self.thread = threading.Thread(target=self.ws.run_forever, daemon=True)
        self.thread.start()

        try:
            while True:time.sleep(1)
        except KeyboardInterrupt:
            print('中斷中...')
            self.ws.close()
            self.thread.join()
            print('中斷成功')

        


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


    def place_order(self, action):
        print(f'try {action}')
        return 
        """ 下單交易（買入或賣出） """
        params = {
            "action": action,  # "BUY" 或 "SELL"
            "amount": str(self.order_size),  # 購買數量
            "timestamp": int(time.time() * 1000),
            "type": "MARKET",  # "LIMIT" (限價) 或 "MARKET" (市價)
            "timeInForce": "POST_ONLY",
        }
    
        headers = self.get_headers(params)
        url = f"{BASE_URL}/orders/{self.pair}"
    
        response = requests.post(url, json=params, headers=headers)
        print(response.json())
        
        if response is not None:
            return json.dumps(response, indent=2)
        else:
            return json.dumps({'created failed' : 'bito server no response'})
    
    def stop(self):
        self.ws.close()
        self.thread.join()

        
wsm = trade_ws_manager()
wsm.start('btc_twd', 0.001, 0.001, 0.001)

import json
import logging
import requests
from decimal import Decimal
from functools import wraps

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login
from django.contrib.auth.decorators import login_required

from .bito import get_balance
from .ws import TradeWSManager, EMAIL
from .models import Trade

# 設定 logger
logger = logging.getLogger(__name__)

# 建立全域的 TradeWSManager 實例
trade_ws_manager = TradeWSManager()

def json_login_required(view_func):
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
         if not request.user.is_authenticated:
             return JsonResponse({'success': False, 'error': '未授權，請先登入'}, status=200)
         return view_func(request, *args, **kwargs)
    return _wrapped_view

@csrf_exempt
def balance(request):
    if not request.user.is_authenticated:
        return JsonResponse({'success': False, 'error': '未授權，請先登入'}, status=200)
    try:
        balance_val = get_balance()
        return JsonResponse({'success': True, 'data': {'balance': balance_val}}, status=200)
    except ValueError as e:
        logger.error(f"balance ValueError: {e}")
        return JsonResponse({'success': False, 'error': str(e)}, status=200)
    except Exception as e:
        logger.exception("Internal Server Error in balance")
        return JsonResponse({'success': False, 'error': 'Internal Server Error'}, status=200)

@csrf_exempt
def get_pairs(request):
    try:
        url = 'https://api.bitopro.com/v3/provisioning/trading-pairs'
        response = requests.get(url)
        if response.status_code == 200:
            data = response.json()
            return JsonResponse({'success': True, 'data': data}, status=200)
        else:
            logger.error(f"get_pairs error: status_code {response.status_code}")
            return JsonResponse({'success': False, 'error': '找不到 tickers'}, status=200)
    except Exception as e:
        logger.exception("Internal Server Error in get_pairs")
        return JsonResponse({'success': False, 'error': 'Internal Server Error'}, status=200)

@csrf_exempt
def login_view(request):
    if request.method == "POST":
        try:
            if request.content_type == "application/json":
                data = json.loads(request.body)
            else:
                data = request.POST
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "JSON 格式錯誤"}, status=200)
        username = data.get("username")
        password = data.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return JsonResponse({"success": True, "data": {"message": "登入成功！", "redirect_url": "/"}}, status=200)
        else:
            return JsonResponse({"success": False, "error": "登入失敗，請檢查您的帳號和密碼"}, status=200)
    else:
        return render(request, "login.html")

def home(request):
    if request.user.is_authenticated:
        return render(request, 'index.html')
    else:
        return redirect('login_view')

@csrf_exempt
@json_login_required
def start_trade(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "JSON 格式錯誤"}, status=200)
        pair = data.get('symbol')
        order_size = data.get('order_size')
        try:
            up = float(data.get('price_up_percentage')) * 0.01
            down = float(data.get('price_down_percentage')) * 0.01
        except (TypeError, ValueError) as e:
            logger.error(f"start_trade percentage error: {e}")
            return JsonResponse({"success": False, "error": "價格百分比格式錯誤"}, status=200)
        try:
            resp = trade_ws_manager.start(
                pair=pair,
                order_size=order_size,
                price_increase_percentage=up,
                price_decrease_percentage=down,
                user=request.user
            )
            if resp == 0:
                return JsonResponse({'success': True, 'data': trade_ws_manager.get_manager_state()}, status=200)
            else:
                return JsonResponse({'success': False, 'error': resp}, status=200)
        except Exception as e:
            logger.exception("Internal Server Error in start_trade")
            return JsonResponse({'success': False, 'error': str(e)}, status=200)
    else:
        return JsonResponse({"success": False, "error": "只接受 POST 方法"}, status=200)

@csrf_exempt
@json_login_required
def stop_trade(request):
    if request.method == 'POST':
        try:
            resp = trade_ws_manager.stop()
            if resp == 0:
                return JsonResponse({"success": True, "data": {"message": "交易機器人已停止"}}, status=200)
            else:
                return JsonResponse({'success': False, 'error': resp}, status=200)
        except Exception as e:
            logger.exception("Internal Server Error in stop_trade")
            return JsonResponse({"success": False, "error": "Internal Server Error"}, status=200)
    else:
        return JsonResponse({"success": False, "error": "只接受 POST 方法"}, status=200)

@csrf_exempt
@json_login_required
def update_trade(request):
    if request.method == 'POST':
        try:
            data = json.loads(request.body)
        except json.JSONDecodeError:
            return JsonResponse({"success": False, "error": "JSON 格式錯誤"}, status=200)
        order_size = data.get('order_size')
        try:
            up = float(data.get('price_up_percentage')) * 0.01
            down = float(data.get('price_down_percentage')) * 0.01
        except (TypeError, ValueError) as e:
            logger.error(f"update_trade percentage error: {e}")
            return JsonResponse({"success": False, "error": "價格百分比格式錯誤"}, status=200)
        try:
            resp = trade_ws_manager.update(
                order_size=order_size,
                price_increase_percentage=up,
                price_decrease_percentage=down
            )
            if resp == 0:
                return JsonResponse({'success': True, 'data': trade_ws_manager.get_manager_state()}, status=200)
            else:
                return JsonResponse({'success': False, 'error': resp}, status=200)
        except Exception as e:
            logger.exception("Internal Server Error in update_trade")
            return JsonResponse({"success": False, "error": "Internal Server Error"}, status=200)
    else:
        return JsonResponse({"success": False, "error": "只接受 POST 方法"}, status=200)

@csrf_exempt
@json_login_required
def check_trade(request):
    if request.method == 'GET':
        try:
            if trade_ws_manager.is_running:
                return JsonResponse({'success': True, 'data': trade_ws_manager.get_manager_state()}, status=200)
            else:
                return JsonResponse({'success': False, 'error': '機器人未啟動/已停止'}, status=200)
        except Exception as e:
            logger.exception("Internal Server Error in check_trade")
            return JsonResponse({"success": False, "error": "Internal Server Error"}, status=200)
    else:
        return JsonResponse({"success": False, "error": "只接受 GET 方法"}, status=200)
    
@csrf_exempt
@json_login_required
def get_fee(request):
    if request.method == 'GET':
        try:
            trades = Trade.objects.filter(user_email=EMAIL)
            usdt_fee = 0
            twd_fee = 0

            for trade in trades:
                if (trade.fee_symbol == 'twd'):
                    twd_fee += trade.fee
                elif (trade.fee_symbol == 'usdt'):
                    usdt_fee += trade.fee
                elif (trade.fee_symbol != 'usdt' or trade.fee_symbol != 'twd'):
                    if trade.pair.find('usdt') != -1:
                        usdt_fee += trade.price * trade.fee
                    elif trade.pair.find('twd') != -1:
                        twd_fee += trade.price * trade.fee
                    

            print(f'twd_fee : {twd_fee}')
            print(f'usdt_fee: {usdt_fee}')
            return JsonResponse(
                {
                    "response":{
                            "status" : "success", 
                            "message" : "get fee",
                            "data" : {
                                "twd_fee" : float(twd_fee),
                                "usdt_fee" : float(usdt_fee)
                            }
                    },
                    "code" : "200"
                }
            )
        except Exception as e:
            logger.exception("Internal Server Error in get_fee")
            return JsonResponse(
            {
                "response":{
                    "status" : "error", 
                    "message" : f"error message from get_fee : {e}",
                    "data" : {}
                },
                "code" : "400"
            }
        )
    else:
        return JsonResponse(
            {
                "response":{
                    "status" : "error", 
                    "message" : "只接受 GET 方法",
                    "data" : {}
                },
                "code" : "400"
            }
        )

@csrf_exempt
@json_login_required
def get_profit(request):
    if request.method == 'GET':
        try:
            pair_profit_dict = {}
            url = 'https://api.bitopro.com/v3/provisioning/trading-pairs'
            response = requests.get(url)
            datas = response.json().get('data')
            for data in datas:
                pair = data.get('pair')
                pair_profit_dict[pair] = get_pair_profit(pair)

            return JsonResponse(
                {
                    "response":{
                            "status" : "success", 
                            "message" : "get profit",
                            "data" : pair_profit_dict
                    },
                    "code" : "200"
                }
            )
        except Exception as e:
            logger.exception("Internal Server Error in get_profit")
            return JsonResponse(
            {
                "response":{
                    "status" : "error", 
                    "message" : f"error message from get_profit : {e}",
                    "data" : {}
                },
                "code" : "400"
            }
        )
    else:
        return JsonResponse(
            {
                "response":{
                    "status" : "error", 
                    "message" : "只接受 GET 方法",
                    "data" : {}
                },
                "code" : "400"
            }
        )
    
def get_pair_profit(pair):
    buy_trades = Trade.objects.filter(user_email=EMAIL, pair=pair, action = 'BUY').order_by('trade_date')
    sell_trades = Trade.objects.filter(user_email=EMAIL, pair=pair, action = 'SELL').order_by('trade_date')

    profit = Decimal('0')
    buy_index = 0
    buy_qty = Decimal('0')
    buy_price = Decimal('0')

    for sell in sell_trades:
        sell_qty = sell.quantity
        sell_price = sell.price
        print(f'SELL: {sell_qty} @ {sell_price}')

        while (sell_qty > 0 and (buy_index < len(buy_trades) or buy_qty > 0)):

            if buy_qty <= 0:
                buy = buy_trades[buy_index]
                buy_qty = buy.quantity
                buy_price = buy.price
                buy_index += 1
                continue
            
            matched_qty = min(sell_qty, buy_qty)
            profit += matched_qty * (sell_price - buy_price)
            sell_qty -= matched_qty
            buy_qty -= matched_qty

        if sell_qty > 0:
            print('異常 : 出現未匹配的賣出單據')
        
    return profit
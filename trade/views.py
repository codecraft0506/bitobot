import json
import logging
import requests
from decimal import Decimal
from functools import wraps

from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login
from django.utils import timezone

from .binance import get_account_balance, get_all_pairs
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
        balance_val = get_account_balance()
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
        result = trade_ws_manager.get_all_pairs()
        if type(result) == list:
            return JsonResponse({'success': True, 'data': result}, status=200)
        else:
            return JsonResponse({'success': False, 'data': result['message']})
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
            return JsonResponse({"success": False, "error": "JSON 格式錯誤"}, status=400)
        pair = data.get('symbol')
        order_size = data.get('order_size')
        try:
            up = float(data.get('price_up_percentage')) * 0.01
            down = float(data.get('price_down_percentage')) * 0.01
        except (TypeError, ValueError) as e:
            logger.error(f"start_trade percentage error: {e}")
            return JsonResponse({"success": False, "error": "價格百分比格式錯誤"}, status=400)
        try:
            trade_count = int(data.get('trade_count')) # 一次開多單
        except e:
            logger.error(f'start_trade trade_count error: {e}')
            return JsonResponse({"success": False, "error": {e}}, status=400)
        
        try:
            price_reset_cv = float(data.get('price_reset_cv')) * 0.01 # 劇烈波動風控重設值
            price_cancel_cv = float(data.get('price_cancel_cv')) * 0.01 # 劇烈波動風控取消值
            if price_reset_cv >= price_cancel_cv:
                return JsonResponse({"success": False, "error" : "風控中斷值必須大於風控重設值!"}, status=400)
        except (TypeError, ValueError) as e:
            logger.error(f"start_trade price_cv error: {e}")
            return JsonResponse({"success": False, "error": "波動百分比格式錯誤"}, status=400)

        try:
            resp = trade_ws_manager.start(
                pair=pair,
                order_size=order_size,
                price_increase_percentage=up,
                price_decrease_percentage=down,
                user=request.user,
                trade_count=trade_count,
                price_reset_cv=price_reset_cv,
                price_cancel_cv=price_cancel_cv,
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
            return JsonResponse({"success": False, "error": "JSON 格式錯誤"}, status=400)
        order_size = data.get('order_size')
        try:
            up = float(data.get('price_up_percentage')) * 0.01
            down = float(data.get('price_down_percentage')) * 0.01
        except (TypeError, ValueError) as e:
            logger.error(f"update_trade percentage error: {e}")
            return JsonResponse({"success": False, "error": "價格百分比格式錯誤"}, status=400)
        try:
            trade_count = int(data.get('trade_count')) # 一次開多單
        except e:
            logger.error(f'start_trade trade_count error: {e}')
            return JsonResponse({"success": False, "error": {e}}, status=400)
        
        try:
            price_reset_cv = float(data.get('price_reset_cv')) * 0.01 # 劇烈波動風控重設值
            price_cancel_cv = float(data.get('price_cancel_cv')) * 0.01 # 劇烈波動風控取消值
            if price_reset_cv >= price_cancel_cv:
                return JsonResponse({"success": False, "error" : "風控中斷值必須大於風控重設值!"}, status=400)
        except (TypeError, ValueError) as e:
            logger.error(f"start_trade price_cv error: {e}")
            return JsonResponse({"success": False, "error": "波動百分比格式錯誤"}, status=400)
        try:
            resp = trade_ws_manager.update(
                order_size=order_size,
                price_increase_percentage=up,
                price_decrease_percentage=down,
                trade_count=trade_count,
                price_reset_cv=price_reset_cv,
                price_cancel_cv=price_cancel_cv,
            )
            if resp == 0:
                return JsonResponse({'success': True, 'data': trade_ws_manager.get_manager_state()}, status=200)
            else:
                return JsonResponse({'success': False, 'error': resp}, status=400)
        except Exception as e:
            logger.exception("Internal Server Error in update_trade")
            return JsonResponse({"success": False, "error": "Internal Server Error"}, status=400)
    else:
        return JsonResponse({"success": False, "error": "只接受 POST 方法"}, status=400)

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
def get_trades(request):
    if request.method == 'GET':
        try:
            result = []
            pairs = trade_ws_manager.get_all_pairs()
            for pair in pairs:
                result.extend(get_trades_by_pair(pair))
            result.sort(key=lambda x : x['trade_date'], reverse=True)

            return JsonResponse(
                {
                    "response":{
                        "status" : "success", 
                        "message" : f"get trades",
                        "data" : result
                    },
                    "code" : "400"
                }
            )
        except Exception as e:
            logger.exception("Internal Server Error in get_trades")
            return JsonResponse(
                {
                    "response":{
                        "status" : "error", 
                        "message" : f"error message from get_trades : {e}",
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
    
def get_trades_by_pair(pair):
    buy_trades = Trade.objects.filter(user_email=EMAIL, pair=pair, action = 'BUY').order_by('trade_date')
    sell_trades = Trade.objects.filter(user_email=EMAIL, pair=pair, action = 'SELL').order_by('trade_date')

    result = [
                {
                    "id" : trade.id,
                    "pair" : trade.pair,
                    "action" : trade.action, 
                    "price" : float(trade.price),
                    "fee" : float(trade.fee),
                    "fee_symbol" : trade.fee_symbol,
                    "quantity" : float(trade.quantity),
                    "trade_date" : timezone.localtime(trade.trade_date).strftime("%Y-%m-%d %H:%M:%S")
                } for trade in buy_trades
            ]


    buy_index = 0
    buy_qty = Decimal('0')
    buy_price = Decimal('0')

    for sell in sell_trades:
        sell_qty = sell.quantity
        sell_price = sell.price
        profit = Decimal('0')

        while (sell_qty > 0 and (buy_index < len(buy_trades) or buy_qty > 0)):

            if buy_qty <= 0:
                buy = buy_trades[buy_index]
                buy_qty = buy.quantity
                buy_price = buy.price
                buy_index += 1
                continue
            
            matched_qty = min(sell_qty, buy_qty)
            profit += matched_qty * (sell_price - buy_price)
            profit -= sell.fee
            profit -= buy.fee * (matched_qty / buy_qty)
            sell_qty -= matched_qty
            buy_qty -= matched_qty

        result.append(
            {
                "id" : sell.id,
                "pair" : sell.pair,
                "action" : sell.action, 
                "price" : float(sell.price),
                "fee" : float(sell.fee),
                "fee_symbol" : sell.fee_symbol,
                "quantity" : float(sell.quantity),
                "trade_date" : timezone.localtime(sell.trade_date).strftime("%Y-%m-%d %H:%M:%S"),
                "profit" : profit
            }
        )

        if sell_qty > 0:
            print('異常 : 出現未匹配的賣出單據')
        
    return result

@csrf_exempt
@json_login_required
def get_spots(request):
    if request.method == 'GET':
        try:
            result = []
            pairs = trade_ws_manager.get_all_pairs()
            for pair in pairs:
                result.extend(get_spots_by_pair(pair))
            result.sort(key=lambda x : x['trade_date'], reverse=True)

            return JsonResponse(
                {
                    "response":{
                        "status" : "success", 
                        "message" : f"get trades",
                        "data" : result
                    },
                    "code" : "400"
                }
            )
        except Exception as e:
            logger.exception("Internal Server Error in get_spots")
            return JsonResponse(
            {
                "response":{
                    "status" : "error", 
                    "message" : f"error message from get_spots : {e}",
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
    
def get_spots_by_pair(pair):
    buy_trades = Trade.objects.filter(
        user_email=EMAIL,
        action='BUY',
        pair=pair,
    ).order_by('pair').order_by('trade_date')

    sell_trades = Trade.objects.filter(
        user_email=EMAIL,
        action='SELL',
        pair=pair,
    ).order_by('pair').order_by('trade_date')

    # 計算總買入量與總賣出量
    total_buy_qty = sum(b.quantity for b in buy_trades)
    total_sell_qty = sum(s.quantity for s in sell_trades)

    remaining_qty = total_buy_qty - total_sell_qty

    result = []
    qty_needed = remaining_qty
    buy_trades = reversed(buy_trades)

    for trade in buy_trades:
        if qty_needed <= 0:
            break
        
        if trade.quantity <= qty_needed:
            result.append({
                "id": trade.id,
                "pair": trade.pair,
                "price": float(trade.price),
                "quantity": float(trade.quantity) - float(trade.fee),
                "trade_date": timezone.localtime(trade.trade_date).strftime("%Y-%m-%d %H:%M:%S")
            })
            qty_needed -= trade.quantity
        else:
            result.append({
                "id": trade.id,
                "pair": trade.pair,
                "price": float(trade.price),
                "quantity": float(qty_needed),  # ⚠️ 僅回傳剩下那一點點
                "trade_date": timezone.localtime(trade.trade_date).strftime("%Y-%m-%d %H:%M:%S")
            })
            qty_needed = Decimal('0.0')

    return result

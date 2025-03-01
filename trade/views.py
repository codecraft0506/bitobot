from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login
from django.http import StreamingHttpResponse

import requests
import json

from .models import OrderHistory
from .bito import get_balance
from .ws import TradeWSManager

@csrf_exempt
def balance(request):
    """取得帳戶餘額"""
    return JsonResponse({'status': True, 'message' : get_balance()})

@csrf_exempt
def get_pairs(request):
    url = 'https://api.bitopro.com/v3/tickers'
    response = requests.get(url)
    if response.status_code == 200:
        data = response.json()
        # 可選：回傳全部資料或只回傳交易對列表
        return JsonResponse(data)
    else:
        return JsonResponse({'status': False, 'message': '找不到 tickers'})


@csrf_exempt
def login_view(request):
    if request.method == "POST":
        if request.content_type == "application/json":
            data = json.loads(request.body)
        else:
            data = request.POST
        username = data.get("username")
        password = data.get("password")
        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)
            return JsonResponse({"message": "登入成功！", "redirect_url": "/"})
        else:
            return JsonResponse({"error": "登入失敗，請檢查您的帳號和密碼"}, status=400)
    else:
        return render(request, "login.html")


def home(request):
    """
    首頁：若已登入則進入交易介面，否則轉跳到登入頁面
    """
    if request.user.is_authenticated:
        return render(request, 'index.html')
    else:
        return redirect('login_view')


@csrf_exempt
def start_trade(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        pair = data.get('symbol')
        order_size = data.get('order_size')
        up = float(data.get('price_up_percentage')) * 0.01
        down = float(data.get('price_down_percentage')) * 0.01
        # 單例模式：取得全域唯一的交易機器人管理物件
        wsm = TradeWSManager()
        response = wsm.start(pair=pair, order_size=order_size,
                             price_increase_percentage=up, price_decrease_percentage=down, user=request.user)
        if response == 0:
            return JsonResponse({'status': True, 'data': wsm.get_manager_state()})
        else:
            print(response)
            return JsonResponse({'status': False, 'message': response}, status=400)


@csrf_exempt
def stop_trade(request):
    if request.method == 'POST':
        wsm = TradeWSManager()
        response = wsm.stop()
        if response == 0:
            return JsonResponse({"status": True, 'message': '交易機器人已停止'})
        else:
            print(response)
            return JsonResponse({'status': False, 'message': response}, status=400)


@csrf_exempt
def update_trade(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        order_size = data.get('order_size')
        up = float(data.get('price_up_percentage')) * 0.01
        down = float(data.get('price_down_percentage')) * 0.01
        wsm = TradeWSManager()
        response = wsm.update(order_size=order_size,
                              price_increase_percentage=up, price_decrease_percentage=down)
        if response == 0:
            return JsonResponse({'status': True, 'data': wsm.get_manager_state()})
        else:
            print(response)
            return JsonResponse({'status': False, 'message': response}, status=400)


@csrf_exempt
def check_trade(request):
    if request.method == 'POST':
        wsm = TradeWSManager()
        if wsm.is_running:
            return JsonResponse({'status' : True, 'message' : wsm.get_manager_state()})
        else:
            return JsonResponse({'status' : False, 'messsage' : '機器人未啟動/已停止'})
        
@csrf_exempt
def get_order_history(request):
    user = request.user  # 取得當前登入的使用者
    orders = OrderHistory.objects.filter(user=user).values("id", "timestamp", "symbol", "price", "order_type", "quantity")
    return JsonResponse({'status' : True , 'message': list(orders)}, safe=False)

@csrf_exempt
def event_log(request):
    wsm = TradeWSManager()
    return StreamingHttpResponse(wsm.log())

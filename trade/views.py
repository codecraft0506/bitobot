from django.shortcuts import render, redirect
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.contrib.auth import authenticate, login, logout
from django.contrib import messages
import requests

import json
from .bito import get_balance, get_open_orders
from .ws import TradeWSManager

@csrf_exempt
def balance(request):
    """ 取得帳戶餘額 """
    return JsonResponse(get_balance())

@csrf_exempt
def check_orders(request):
    return JsonResponse(get_open_orders('btc_twd'))

@csrf_exempt
def get_pairs(request):
    url = 'https://api.bitopro.com/v3/tickers'
    response = requests.get(url)

    if response.status_code == 200:
        data = response.json()
        pairs = [item["pair"] for item in data["data"]]
        print(pairs)
        return JsonResponse(data)
    else:
        return JsonResponse({'錯誤訊息':'找不到 tickers'})


@csrf_exempt
def login_view(request):
    if request.method == "POST":
        data = json.loads(request.body) if request.content_type == "application/json" else request.POST
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
    首頁：若已登入則進入交易介面，否則重導向到登入
    """
    if request.user.is_authenticated:
        return render(request, 'index.html')
    else:
        return redirect('login_view')
    


@csrf_exempt
def start_trade(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        pair = data.get('pair')
        order_size = data.get('order_size')
        up = data.get('price_up_percentage')
        down = data.get('price_down_percentage')
    
        # 此處使用了單例模式 不是寫錯
        wsm = TradeWSManager()
        response = wsm.start(pair=pair, order_size=order_size, price_increase_percentage=up, price_decrease_percentage=down)
    
        if response == 0: return JsonResponse({'status':'交易機器人成功啟動', 'message': wsm.check_mangaer_state()})
        else : return JsonResponse({'status':'交易機器人啟動失敗' , 'message': 'wrong: in trade/views.py/start_trade'})

@csrf_exempt
def stop_trade(request):
    if request.method == 'POST':
        # 此處使用了單例模式 不是寫錯
        wsm = TradeWSManager()
        response = wsm.stop()

        if response == 0 : return JsonResponse({"status": "交易機器人已停止"})
        else : return JsonResponse({'status':'交易機器人停止失敗' , 'message': 'wrong: in trade/views.py/stop_trade'})

@csrf_exempt
def update_trade(request):
    if request.method == 'POST':
        data = json.loads(request.body)
        pair = data.get('pair')
        order_size = data.get('order_size')
        up = data.get('price_up_percentage')
        down = data.get('price_down_percentage')

        # 此處使用了單例模式 不是寫錯
        wsm = TradeWSManager()
        response = wsm.update(order_size=order_size, price_increase_percentage=up, price_decrease_percentage=down)

        if response == 0 : return JsonResponse({"status": "交易機器人已停止"})
        else : return JsonResponse({'status':'交易機器人停止失敗' , 'message': 'wrong: in trade/views.py/stop_trade'})

@csrf_exempt
def check_trade(request):
    if request.method == 'POST':
        wsm = TradeWSManager()
        return wsm.check_mangaer_state()

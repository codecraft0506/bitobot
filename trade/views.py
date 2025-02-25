from django.shortcuts import render
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
import json
from .bito import get_balance, place_order, get_open_orders, cancel_order

@csrf_exempt
def balance(request):
    """ 取得帳戶餘額 """
    return JsonResponse(get_balance())

@csrf_exempt
def buy(request):
    """ 掛買單 """
    if request.method == "POST":
        data = json.loads(request.body)
        pair = data.get("pair", "btc_twd")  # 幣對，例如 BTC/TWD
        price = data.get("price", 1000000)  # 價格
        amount = data.get("amount", 0.01)  # 買入數量
        return JsonResponse(place_order(pair, "BUY", price, amount))

@csrf_exempt
def sell(request):
    """ 掛賣單 """
    if request.method == "POST":
        data = json.loads(request.body)
        pair = data.get("pair", "btc_twd")
        price = data.get("price", 1200000)
        amount = data.get("amount", 0.01)
        return JsonResponse(place_order(pair, "SELL", price, amount))

@csrf_exempt
def orders(request):
    """ 取得未完成掛單 """
    if request.method == "GET":
        pair = request.GET.get("pair", "btc_twd")
        return JsonResponse(get_open_orders(pair))

@csrf_exempt
def cancel(request):
    """ 取消指定掛單 """
    if request.method == "POST":
        data = json.loads(request.body)
        pair = data.get("pair", "btc_twd")
        order_id = data.get("order_id")
        return JsonResponse(cancel_order(pair, order_id))
    
@csrf_exempt
def submit_order(request):
    if request.method == "POST":
        try:
            data = json.loads(request.body)
            return JsonResponse({"status": "success", "data": data})
        except Exception as e:
            return JsonResponse({"status": "error", "message": str(e)}, status=400)
    return JsonResponse({"error": "Invalid request"}, status=400)

def trade_form(request):
    """ 回應 HTML 表單"""
    return render(request, 'trade.html')
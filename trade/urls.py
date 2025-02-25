from django.urls import path
from .views import *

urlpatterns = [
    path("balance/", balance, name="balance"),
    path("buy/", buy, name="buy"),
    path("sell/", sell, name="sell"),
    path("orders/", orders, name="orders"),
    path("cancel/", cancel, name="cancel"),
    path("form/", trade_form, name="trade_form"),
    path("submit-order/", submit_order, name="submit_order"),
]

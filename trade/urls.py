from django.urls import path
from .views import *

urlpatterns = [
    path('', home, name='home'),
    path('login/', login_view, name="login_view"),
    path("pairs/", get_pairs, name="pairs"),                
    path("balance/", balance, name="balance"),            
    path('orders/', get_open_orders, name='orders'),
    path('start_trade', start_trade, name='start_trade'),     # 開啟機器人
    path('stop_trade', stop_trade, name='stop_trade'),        # 關閉機器人
    path('update_trade', update_trade, name='update_trade'),  # 更新機器人參數
    path('check_trade', check_trade, name='check_trade'),     # 查看機器人參數
]

from django.urls import path
from .views import (
    home, login_view, get_pairs, balance,
    start_trade, stop_trade, update_trade, check_trade,
    get_trades, get_spots,
)

urlpatterns = [
    path('', home, name='home'),
    path('login/', login_view, name="login_view"),
    path('get_pairs/', get_pairs, name="get_pairs"),
    path('balance/', balance, name="balance"),
    path('start_trade/', start_trade, name='start_trade'),
    path('stop_trade/', stop_trade, name='stop_trade'),
    path('update_trade/', update_trade, name='update_trade'),
    path('check_trade/', check_trade, name='check_trade'),
    path('get_trades/', get_trades, name='get_trades'),
    path('get_spots/', get_spots, name='get_spots'),
]

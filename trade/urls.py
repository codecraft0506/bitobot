from django.urls import path
from .views import (
    home, login_view, get_pairs, balance,
    start_trade, stop_trade, update_trade, check_trade, submit_order, get_order_history, event_log
)

urlpatterns = [
    path('', home, name='home'),
    path('login/', login_view, name="login_view"),
    path('pairs/', get_pairs, name="pairs"),
    path('balance/', balance, name="balance"),
    path('start_trade', start_trade, name='start_trade'),
    path('stop_trade', stop_trade, name='stop_trade'),
    path('update_trade', update_trade, name='update_trade'),
    path('check_trade', check_trade, name='check_trade'),
    path('submit-order/', submit_order, name='submit_order'),
    path('history/', get_order_history, name='history'),
    path('event/', event_log, name='event'),
]

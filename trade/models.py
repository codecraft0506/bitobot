from django.db import models
from django.contrib.auth.models import User

ACTION_CHOICE = [
    ('BUY', 'BUY'),
    ('SELL', 'SELL'),
]

class Trade(models.Model):
    user_email = models.CharField(max_length=50, null=True)
    id = models.CharField(max_length=20, primary_key=True)
    pair = models.CharField(max_length=10)
    action = models.CharField(max_length=10, choices=ACTION_CHOICE, null=True)
    quantity = models.DecimalField(max_digits=20, decimal_places=10)
    price = models.DecimalField(max_digits=20, decimal_places=10)
    fee = models.DecimalField(max_digits=20, decimal_places=10)
    fee_symbol = models.CharField(max_length=10, default='twd')
    trade_date = models.DateTimeField(auto_now_add=True)
    trade_or_not = models.BooleanField(default=False)

class SpotTrade(models.Model):
    user_email = models.CharField(max_length=50, null=True)
    id = models.CharField(max_length=20, primary_key=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=8)
    pair = models.CharField(max_length=10)
    open_position = models.DecimalField(max_digits=10, decimal_places=8)
    sold_price = models.DecimalField(max_digits=10, decimal_places=8)
    sold_or_not = models.BooleanField(default=False)
    profit = models.DecimalField(max_digits=10, decimal_places=8)
    fee = models.DecimalField(max_digits=10, decimal_places=8)
    fee_symbol = models.CharField(max_length=10, default='twd')
    exceed_or_not = models.BooleanField(default=False)
    target_after_exceed = models.DecimalField(max_digits=10, decimal_places=8)
from django.db import models

class Trade(models.Model):
    id = models.AutoField(primary_key=True)
    pair = models.CharField(max_length=10)
    method = models.CharField(max_length=10, choices=['買入', '賣出'])
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    price = models.DecimalField(max_digits=10, decimal_places=2)
    fee = models.DecimalField(max_digits=10, decimal_places=2)
    trade_date = models.DateTimeField(auto_now_add=True)
    trade_or_not = models.BooleanField(default=False)

class SpotTrade(models.Model):
    id = models.AutoField(primary_key=True)
    quantity = models.DecimalField(max_digits=10, decimal_places=2)
    pair = models.CharField(max_length=10)
    open_position = models.DecimalField(max_digits=10, decimal_places=2)
    sold_price = models.DecimalField(max_digits=10, decimal_places=2)
    sold_or_not = models.BooleanField(default=False)
    profit = models.DecimalField(max_digits=10, decimal_places=2)
    fee = models.DecimalField(max_digits=10, decimal_places=2)
    exceed_or_not = models.BooleanField(default=False)
    target_after_exceed = models.DecimalField(max_digits=10, decimal_places=2)
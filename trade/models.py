from django.db import models
from django.contrib.auth.models import User

class OrderHistory(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE)  # 連接到 User
    order_id = models.CharField(max_length=50, unique=True)    # Bito 訂單 id (設定為唯一)
    timestamp = models.DateTimeField()                         # 訂單時間
    symbol = models.CharField(max_length=10)                   # 交易對，例如 BTC
    price = models.DecimalField(max_digits=20, decimal_places=8) # 訂單價格
    order_type = models.CharField(max_length=4, choices=[("BUY", "BUY"), ("SELL", "SELL")])  # 訂單類型
    quantity = models.DecimalField(max_digits=20, decimal_places=8) # 訂單數量

    def __str__(self):
        return f"{self.user.username} - {self.symbol} {self.order_type} {self.quantity} @ {self.price} (Order ID: {self.order_id})"

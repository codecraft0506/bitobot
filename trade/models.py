from django.db import models
from django.contrib.auth.models import User

class TransactionStatus(models.Model):
    profile = models.ForeignKey(User, on_delete=models.CASCADE)
    status = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=10, decimal_places=2)  # 交易金額
    currency = models.CharField(max_length=10, choices=[("USD", "USD"), ("BTC", "BTC"), ("ETH", "ETH")])
    recipient = models.CharField(max_length=255, blank=True, null=True)  # 交易對象
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.profile.user.username} - {self.status}"

    def __str__(self):
        return f"{self.profile.user.username} - {self.status}"
# app/forms.py
from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User
# from .models import UserProfile, Link

class CustomUserCreationForm(UserCreationForm):
    email = forms.EmailField(required=True)  # 新增電子郵件欄位

    class Meta:
        model = User
        fields = ("username", "email", "password1", "password2")

    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data['email']  # 保存電子郵件
        if commit:
            user.save()
        return user

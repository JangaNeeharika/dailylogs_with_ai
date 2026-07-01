import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'dailylogs.settings')
django.setup()

from django.core.mail import send_mail
from django.conf import settings

print("BACKEND:", settings.EMAIL_BACKEND)
print("HOST:", settings.EMAIL_HOST)
print("USER:", settings.EMAIL_HOST_USER)
print("PASSWORD starts with:", settings.EMAIL_HOST_PASSWORD[:4])

result = send_mail(
    'OTP Test',
    'Your OTP is 123456',
    None,
    ['janganeeharika@gmail.com'],
    fail_silently=False
)
print("SUCCESS, result:", result)
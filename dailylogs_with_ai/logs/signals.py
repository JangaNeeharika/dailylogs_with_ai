from django.db.models.signals import post_save
from django.contrib.auth.models import User
from django.dispatch import receiver
from .models import Profile

MEMBER_COLORS = [
    '#3a6b4d', '#2d5fa0', '#7b4fa0', '#b5451b',
    '#c98b2a', '#1a7a7a', '#8b3a8b', '#c44a38',
]

def _assign_color(username):
    h = 0
    for c in username:
        h = (h * 31 + ord(c)) % len(MEMBER_COLORS)
    return MEMBER_COLORS[h]

@receiver(post_save, sender=User)
def create_profile(sender, instance, created, **kwargs):
    if created:
        Profile.objects.get_or_create(
            user=instance,
            defaults={'color': _assign_color(instance.username)}
        )
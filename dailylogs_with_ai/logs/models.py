from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone


class Profile(models.Model):
    ROLE_CHOICES = [('member', 'Member'), ('mentor', 'Mentor')]

    user    = models.OneToOneField(User, on_delete=models.CASCADE, related_name='profile')
    role    = models.CharField(max_length=10, choices=ROLE_CHOICES, default='member')
    college = models.CharField(max_length=200, blank=True)
    color   = models.CharField(max_length=10, blank=True, default='#3a6b4d')

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class Log(models.Model):
    member      = models.ForeignKey(User, on_delete=models.CASCADE, related_name='logs')
    date        = models.DateField()
    title       = models.CharField(max_length=120)
    description = models.TextField(blank=True)
    hours_spent = models.FloatField(default=0)
    tags        = models.CharField(max_length=300, blank=True)   # comma-separated
    created_at  = models.DateTimeField(default=timezone.now)

    class Meta:
        ordering = ['-date', '-created_at']

    def tags_list(self):
        return [t.strip() for t in self.tags.split(',') if t.strip()]

    def __str__(self):
        return f"{self.member.username} | {self.date} | {self.title}"


class Mark(models.Model):
    log    = models.OneToOneField(Log, on_delete=models.CASCADE, related_name='mark')
    mentor = models.ForeignKey(User, on_delete=models.CASCADE, related_name='marks_given')
    stars  = models.PositiveSmallIntegerField(default=0)   # 1-5
    note   = models.CharField(max_length=200, blank=True)
    marked_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Mark for Log#{self.log_id} – {self.stars}★"
    



class ChatMessage(models.Model):
    user = models.ForeignKey(
        User,
        on_delete=models.CASCADE,
        related_name='chat_messages'
    )

    role = models.CharField(
        max_length=20,
        choices=[
            ('user', 'User'),
            ('assistant', 'Assistant'),
        ]
    )

    message = models.TextField()

    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['created_at']
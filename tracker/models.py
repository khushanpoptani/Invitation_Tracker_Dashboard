from django.contrib.auth import get_user_model
from django.db import models
from django.utils import timezone

User = get_user_model()


class ConnectionStatus(models.Model):
    name = models.CharField(max_length=50, unique=True)

    class Meta:
        ordering = ["id"]
        verbose_name_plural = "Connection statuses"

    def __str__(self):
        return self.name


class MessageType(models.Model):
    message_id = models.CharField(max_length=100)
    message = models.TextField()
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="message_types")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username", "message_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["message_id", "user"],
                name="unique_message_id_per_user",
            )
        ]

    def __str__(self):
        return f"{self.message_id} ({self.user.username})"


class FollowUpMessage(models.Model):
    follow_up_message_id = models.CharField(max_length=100)
    message = models.TextField()
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="follow_up_messages")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username", "follow_up_message_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["follow_up_message_id", "user"],
                name="unique_follow_up_message_id_per_user",
            )
        ]

    def __str__(self):
        return f"{self.follow_up_message_id} ({self.user.username})"


class SentConnection(models.Model):
    name = models.CharField(max_length=255)
    profile_link = models.URLField(blank=True)
    message = models.TextField(blank=True)
    message_id = models.CharField(max_length=100, blank=True)
    date = models.DateField(default=timezone.localdate)
    connection_status = models.ForeignKey(
        ConnectionStatus,
        on_delete=models.PROTECT,
        related_name="sent_connections",
    )
    follow_up_message = models.ForeignKey(
        FollowUpMessage,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="sent_connections",
    )
    follow_up_message_1 = models.TextField(blank=True, default="")
    follow_up_message_2 = models.TextField(blank=True, default="")
    follow_up_message_3 = models.TextField(blank=True, default="")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_connections")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.name} - {self.user.username}"

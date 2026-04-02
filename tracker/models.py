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
    message_id = models.CharField(max_length=100)
    follow_up_message_1 = models.TextField(blank=True, default="")
    follow_up_message_2 = models.TextField(blank=True, default="")
    follow_up_message_3 = models.TextField(blank=True, default="")
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="follow_up_messages")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["user__username", "message_id"]
        constraints = [
            models.UniqueConstraint(
                fields=["message_id", "user"],
                name="unique_follow_up_template_message_id_per_user",
            )
        ]

    def __str__(self):
        return f"{self.message_id} ({self.user.username})"


class SentConnection(models.Model):
    PROSPECT_FOLLOW_UP_COMPLETED = "follow_up_completed"
    PROSPECT_NOT_INTERESTED = "not_interested"
    PROSPECT_RESPONDED = "responded"
    PROSPECT_CHOICES = [
        (PROSPECT_FOLLOW_UP_COMPLETED, "Follow Up Completed"),
        (PROSPECT_NOT_INTERESTED, "Not Interested"),
        (PROSPECT_RESPONDED, "Responded"),
    ]

    name = models.CharField(max_length=255)
    profile_link = models.URLField(blank=True)
    message = models.TextField(blank=True)
    message_id = models.CharField(max_length=100, blank=True)
    date = models.DateField(default=timezone.localdate)
    status_date = models.DateField(null=True, blank=True)
    responded = models.BooleanField(default=False)
    prospect = models.CharField(max_length=32, choices=PROSPECT_CHOICES, null=True, blank=True)
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
    follow_up_sent_date_1 = models.DateField(null=True, blank=True)
    follow_up_sent_date_2 = models.DateField(null=True, blank=True)
    follow_up_sent_date_3 = models.DateField(null=True, blank=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name="sent_connections")
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-date", "-id"]

    def __str__(self):
        return f"{self.name} - {self.user.username}"

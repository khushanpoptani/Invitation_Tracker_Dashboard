from django.contrib import admin

from .models import ConnectionStatus, FollowUpMessage, MessageType, SentConnection


@admin.register(ConnectionStatus)
class ConnectionStatusAdmin(admin.ModelAdmin):
    list_display = ("id", "name")
    search_fields = ("name",)


@admin.register(MessageType)
class MessageTypeAdmin(admin.ModelAdmin):
    list_display = ("id", "message_id", "user", "created_at")
    search_fields = ("message_id", "message", "user__username")
    list_filter = ("user",)


@admin.register(FollowUpMessage)
class FollowUpMessageAdmin(admin.ModelAdmin):
    list_display = ("id", "message_id", "user", "created_at")
    search_fields = (
        "message_id",
        "follow_up_message_1",
        "follow_up_message_2",
        "follow_up_message_3",
        "user__username",
    )
    list_filter = ("user",)


@admin.register(SentConnection)
class SentConnectionAdmin(admin.ModelAdmin):
    list_display = (
        "id",
        "name",
        "user",
        "message_id",
        "date",
        "status_date",
        "connection_status",
    )
    search_fields = ("name", "message", "message_id", "user__username")
    list_filter = ("user", "connection_status", "date", "status_date")

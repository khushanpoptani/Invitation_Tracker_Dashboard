from django.apps import AppConfig
from django.db.models.signals import post_migrate


DEFAULT_CONNECTION_STATUSES = ["Pending", "Accepted", "Rejected"]


def ensure_default_statuses(sender, **kwargs):
    from .models import ConnectionStatus

    for status_name in DEFAULT_CONNECTION_STATUSES:
        ConnectionStatus.objects.get_or_create(name=status_name)


class TrackerConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "tracker"

    def ready(self):
        post_migrate.connect(ensure_default_statuses, sender=self)

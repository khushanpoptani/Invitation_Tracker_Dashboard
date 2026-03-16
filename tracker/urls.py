from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("sent-connections/", views.sent_connections_list, name="sent_connections_list"),
    path("message-types/", views.message_type_list, name="message_type_list"),
    path("message-types/next-id/", views.message_type_next_id, name="message_type_next_id"),
    path("message-types/add/", views.message_type_create, name="message_type_create"),
    path("message-types/<int:pk>/edit/", views.message_type_edit, name="message_type_edit"),
    path("message-types/<int:pk>/delete/", views.message_type_delete, name="message_type_delete"),
    path("follow-up-messages/", views.follow_up_message_list, name="follow_up_message_list"),
    path("follow-ups/", views.follow_up_hub, name="follow_up_hub"),
    path(
        "follow-up-messages/sample/",
        views.download_follow_up_template_sample_csv,
        name="download_follow_up_template_sample_csv",
    ),
    path("upload-csv/sample/", views.download_sample_csv, name="download_sample_csv"),
    path("upload-csv/", views.upload_sent_connections_csv, name="upload_sent_connections_csv"),
    path("update-status/", views.update_connection_status, name="update_connection_status"),
    path("users/", views.user_list, name="user_list"),
    path("users/add/", views.user_create, name="user_create"),
    path("users/<int:pk>/", views.user_detail, name="user_detail"),
    path("users/<int:pk>/edit/", views.user_edit, name="user_edit"),
    path("users/<int:pk>/inactive/", views.user_deactivate, name="user_deactivate"),
]

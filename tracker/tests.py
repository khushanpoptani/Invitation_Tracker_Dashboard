from django.contrib.auth import get_user_model
from django.test import Client, TestCase
from django.urls import reverse

from .models import ConnectionStatus, FollowUpMessage, MessageType, SentConnection

User = get_user_model()


class MessageTypeEditSyncTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.admin_user = User.objects.create_user(
            username="admin",
            password="password123",
        )
        self.client.force_login(self.admin_user)

        self.owner = User.objects.create_user(
            username="sunit",
            password="password123",
        )
        self.pending_status, _ = ConnectionStatus.objects.get_or_create(name="Pending")

    def test_editing_message_id_syncs_sent_connections_and_follow_up_templates(self):
        message_type = MessageType.objects.create(
            user=self.owner,
            message_id="1",
            message="Original message text",
        )
        FollowUpMessage.objects.create(
            user=self.owner,
            message_id="1",
            follow_up_message_1="Follow up 1",
            follow_up_message_2="Follow up 2",
            follow_up_message_3="Follow up 3",
        )
        connection = SentConnection.objects.create(
            user=self.owner,
            name="John Doe",
            profile_link="https://example.com/john",
            message="Hello John",
            message_id="1",
            connection_status=self.pending_status,
        )

        response = self.client.post(
            reverse("message_type_edit", args=[message_type.pk]),
            {
                "message_id": "S1",
                "message": "Original message text",
                "user": self.owner.pk,
            },
            follow=True,
        )

        self.assertRedirects(response, reverse("message_type_list"))

        message_type.refresh_from_db()
        connection.refresh_from_db()
        follow_up = FollowUpMessage.objects.get(user=self.owner)

        self.assertEqual(message_type.message_id, "S1")
        self.assertEqual(connection.message_id, "S1")
        self.assertEqual(follow_up.message_id, "S1")

    def test_editing_message_id_is_blocked_when_follow_up_template_target_exists(self):
        message_type = MessageType.objects.create(
            user=self.owner,
            message_id="1",
            message="Message one",
        )
        FollowUpMessage.objects.create(
            user=self.owner,
            message_id="1",
            follow_up_message_1="Old follow up",
        )
        FollowUpMessage.objects.create(
            user=self.owner,
            message_id="S1",
            follow_up_message_1="Conflicting follow up",
        )
        connection = SentConnection.objects.create(
            user=self.owner,
            name="Jane Doe",
            profile_link="https://example.com/jane",
            message="Hello Jane",
            message_id="1",
            connection_status=self.pending_status,
        )

        response = self.client.post(
            reverse("message_type_edit", args=[message_type.pk]),
            {
                "message_id": "S1",
                "message": "Message one",
                "user": self.owner.pk,
            },
        )

        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "That Message ID already exists in Follow Up Templates for this user.")

        message_type.refresh_from_db()
        connection.refresh_from_db()

        self.assertEqual(message_type.message_id, "1")
        self.assertEqual(connection.message_id, "1")

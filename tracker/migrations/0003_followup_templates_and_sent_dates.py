from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0002_sentconnection_follow_up_message_1_and_more"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="followupmessage",
            name="unique_follow_up_message_id_per_user",
        ),
        migrations.AlterModelOptions(
            name="followupmessage",
            options={"ordering": ["user__username", "message_id"]},
        ),
        migrations.RenameField(
            model_name="followupmessage",
            old_name="follow_up_message_id",
            new_name="message_id",
        ),
        migrations.RenameField(
            model_name="followupmessage",
            old_name="message",
            new_name="follow_up_message_1",
        ),
        migrations.AddField(
            model_name="followupmessage",
            name="follow_up_message_2",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddField(
            model_name="followupmessage",
            name="follow_up_message_3",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AlterField(
            model_name="followupmessage",
            name="follow_up_message_1",
            field=models.TextField(blank=True, default=""),
        ),
        migrations.AddConstraint(
            model_name="followupmessage",
            constraint=models.UniqueConstraint(
                fields=("message_id", "user"),
                name="unique_follow_up_template_message_id_per_user",
            ),
        ),
        migrations.AddField(
            model_name="sentconnection",
            name="status_date",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="sentconnection",
            name="follow_up_sent_date_1",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="sentconnection",
            name="follow_up_sent_date_2",
            field=models.DateField(blank=True, null=True),
        ),
        migrations.AddField(
            model_name="sentconnection",
            name="follow_up_sent_date_3",
            field=models.DateField(blank=True, null=True),
        ),
    ]

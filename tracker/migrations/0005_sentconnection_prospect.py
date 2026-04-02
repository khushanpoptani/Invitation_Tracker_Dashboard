from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0004_sentconnection_responded"),
    ]

    operations = [
        migrations.AddField(
            model_name="sentconnection",
            name="prospect",
            field=models.CharField(
                blank=True,
                choices=[
                    ("follow_up_completed", "Follow Up Completed"),
                    ("not_interested", "Not Interested"),
                    ("responded", "Responded"),
                ],
                max_length=32,
                null=True,
            ),
        ),
    ]

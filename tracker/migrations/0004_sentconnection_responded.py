from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("tracker", "0003_followup_templates_and_sent_dates"),
    ]

    operations = [
        migrations.AddField(
            model_name="sentconnection",
            name="responded",
            field=models.BooleanField(default=False),
        ),
    ]

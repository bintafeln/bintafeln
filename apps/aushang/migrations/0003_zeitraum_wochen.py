from django.db import migrations, models


def fahrer_in_wochen(apps, schema_editor):
    """Der Fahrerplan zeigt auf vorhandenen Monitoren künftig die nächsten 9 Wochen ab heute."""
    apps.get_model("aushang", "AushangSeite").objects.filter(art="fahrdienst").update(wochen=9)


class Migration(migrations.Migration):
    dependencies = [
        ("aushang", "0002_rechte"),
    ]

    operations = [
        migrations.AddField(
            model_name="aushangseite",
            name="wochen",
            field=models.PositiveSmallIntegerField(default=0, verbose_name="Wochen"),
        ),
        migrations.RunPython(fahrer_in_wochen, migrations.RunPython.noop),
    ]

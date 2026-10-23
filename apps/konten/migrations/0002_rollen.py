"""Legt die Rollen (Gruppen) von bintafeln an."""

from django.db import migrations

ROLLEN = ("Admin", "Büro", "Ausgabe", "Kiosk")


def anlegen(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    for name in ROLLEN:
        Group.objects.get_or_create(name=name)


def entfernen(apps, schema_editor):
    apps.get_model("auth", "Group").objects.filter(name__in=ROLLEN).delete()


class Migration(migrations.Migration):
    dependencies = [
        ("auth", "0012_alter_user_first_name_max_length"),
        ("konten", "0001_initial"),
    ]

    operations = [migrations.RunPython(anlegen, entfernen)]

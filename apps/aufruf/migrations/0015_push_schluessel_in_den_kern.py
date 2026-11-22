from django.db import migrations, models


def in_den_kern(apps, schema_editor):
    """Der Schlüssel der Tafel zieht um, damit eingeschaltete Benachrichtigungen weiter gelten."""
    alt = apps.get_model("aufruf", "HandyEinstellungen").objects.exclude(push_schluessel="").first()
    if alt is None:
        return
    neu, _ = apps.get_model("core", "PushEinstellungen").objects.get_or_create(pk=1)
    if not neu.schluessel:
        neu.schluessel = alt.push_schluessel
        neu.save()


def zurueck(apps, schema_editor):
    neu = apps.get_model("core", "PushEinstellungen").objects.filter(pk=1).first()
    if neu is None or not neu.schluessel:
        return
    apps.get_model("aufruf", "HandyEinstellungen").objects.update(push_schluessel=neu.schluessel)


class Migration(migrations.Migration):
    dependencies = [
        ("aufruf", "0014_push_nachrichten"),
        ("core", "0035_push_mitarbeitende"),
    ]

    operations = [
        migrations.RunPython(in_den_kern, zurueck),
        migrations.RemoveField(model_name="handyeinstellungen", name="push_schluessel"),
    ]

from django.db import migrations

ALT = "Personal"
NEU = "Angestellte"


def umbenennen(apps, schema_editor):
    """Benennt die mitgelieferte Rolle „Personal“ in „Angestellte“ um (Oberfläche). Die
    zugehörige konten.Rolle hängt über die Gruppen-ID, bleibt also erhalten."""
    Group = apps.get_model("auth", "Group")
    gruppe = Group.objects.filter(name=ALT).first()
    if gruppe and not Group.objects.filter(name=NEU).exists():
        gruppe.name = NEU
        gruppe.save(update_fields=["name"])


def zurueck(apps, schema_editor):
    Group = apps.get_model("auth", "Group")
    gruppe = Group.objects.filter(name=NEU).first()
    if gruppe and not Group.objects.filter(name=ALT).exists():
        gruppe.name = ALT
        gruppe.save(update_fields=["name"])


class Migration(migrations.Migration):
    dependencies = [("konten", "0030_benutzer_listen_spalten_aus")]

    operations = [migrations.RunPython(umbenennen, zurueck)]

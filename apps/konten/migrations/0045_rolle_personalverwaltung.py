from django.db import migrations

ALT = "Angestellte"
NEU = "Personalverwaltung"


def _umbenennen(apps, alt, neu):
    Group = apps.get_model("auth", "Group")
    gruppe = Group.objects.filter(name=alt).first()
    if gruppe and not Group.objects.filter(name=neu).exists():
        gruppe.name = neu
        gruppe.save(update_fields=["name"])


def umbenennen(apps, schema_editor):
    """Die mitgelieferte Rolle „Angestellte“ heißt jetzt „Personalverwaltung“: Sie gibt das Recht,
    Verträge, Stunden und Arbeitszeiten zu verwalten – ob jemand angestellt ist, sagt allein das
    Feld „Beschäftigung“. Rechte und Zuordnungen hängen an der Gruppen-ID und bleiben."""
    _umbenennen(apps, ALT, NEU)


def zurueck(apps, schema_editor):
    _umbenennen(apps, NEU, ALT)


class Migration(migrations.Migration):
    dependencies = [("konten", "0044_listen_filter")]

    operations = [migrations.RunPython(umbenennen, zurueck)]

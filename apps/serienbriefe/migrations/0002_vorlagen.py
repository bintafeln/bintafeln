from django.db import migrations

VORLAGEN = [
    ("Dank für Spenden", "Herzlichen Dank für Ihre Unterstützung im Jahr {jahr}",
     "{anrede}\n\nim Jahr {jahr} haben Sie die {tafel} mit Spenden von insgesamt {spendensumme} "
     "unterstützt. Dafür danken wir Ihnen von Herzen. Ihre Hilfe kommt direkt den Menschen "
     "zugute, die bei uns Lebensmittel erhalten.\n\nMit freundlichen Grüßen\n\n{tafel}"),
    ("Erinnerung Mitgliedsbeitrag", "Ihr Mitgliedsbeitrag {jahr}",
     "{anrede}\n\nnach unseren Unterlagen ist Ihr Mitgliedsbeitrag für {jahr} (Mitgliedsnummer "
     "{mitgliedsnummer}) noch offen: {beitrag_offen}. Falls Sie bereits gezahlt haben, betrachten "
     "Sie dieses Schreiben bitte als gegenstandslos.\n\nVielen Dank für Ihre Unterstützung!\n\n"
     "Mit freundlichen Grüßen\n\n{tafel}"),
    ("Einladung Mitgliederversammlung", "Einladung zur Mitgliederversammlung",
     "{anrede}\n\nhiermit laden wir Sie herzlich zur Mitgliederversammlung der {tafel} ein.\n\n"
     "Termin: …\nOrt: …\n\nTagesordnung:\n1. …\n2. …\n\nMit freundlichen Grüßen\n\n{tafel}"),
]  # fmt: skip


def anlegen(apps, schema_editor):
    vorlage = apps.get_model("serienbriefe", "Vorlage")
    for name, betreff, text in VORLAGEN:
        vorlage.objects.get_or_create(name=name, defaults={"betreff": betreff, "text": text})


def loeschen(apps, schema_editor):
    apps.get_model("serienbriefe", "Vorlage").objects.filter(
        name__in=[v[0] for v in VORLAGEN]
    ).delete()


class Migration(migrations.Migration):
    dependencies = [("serienbriefe", "0001_initial")]

    operations = [migrations.RunPython(anlegen, loeschen)]

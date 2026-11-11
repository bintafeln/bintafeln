"""Mail-Empfänger: statt des Hakens „Niemand bekommt diese Mail“ gibt es in der Auswahl den
Eintrag „wie vorgesehen“. Wer nichts auswählt, wählt damit niemand.

Bestehende Einstellungen bleiben, was sie waren: „niemand“ bleibt niemand; Personen ausgewählt
heißt nur diese Personen; nichts ausgewählt heißt wie vorgesehen.
"""

from django.db import migrations, models

FAHRDIENST = "fahrdienst_ausfall"  # Auswahl liegt in den Fahrdienst-Einstellungen


def _fahrdienst_gewaehlt(apps) -> bool:
    einstellungen = apps.get_model("fahrdienst", "FahrdienstEinstellungen").objects.first()
    return bool(einstellungen) and einstellungen.benachrichtigen.exists()


def vor(apps, schema_editor):
    MailEmpfaenger = apps.get_model("core", "MailEmpfaenger")
    for eintrag in MailEmpfaenger.objects.all():
        if eintrag.niemand:
            eintrag.personen.clear()
            eintrag.vorgabe = False
        elif eintrag.art == FAHRDIENST:
            eintrag.vorgabe = not _fahrdienst_gewaehlt(apps)
        else:
            eintrag.vorgabe = not eintrag.personen.exists()
        eintrag.save(update_fields=["vorgabe"])


def zurueck(apps, schema_editor):
    MailEmpfaenger = apps.get_model("core", "MailEmpfaenger")
    for eintrag in MailEmpfaenger.objects.all():
        gewaehlt = (_fahrdienst_gewaehlt(apps) if eintrag.art == FAHRDIENST
                    else eintrag.personen.exists())  # fmt: skip
        eintrag.niemand = not eintrag.vorgabe and not gewaehlt
        eintrag.save(update_fields=["niemand"])


class Migration(migrations.Migration):
    dependencies = [
        ("core", "0032_mail_niemand"),
        ("fahrdienst", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="mailempfaenger",
            name="vorgabe",
            field=models.BooleanField(
                default=True,
                help_text="Die Mail geht an die vorgesehenen Empfänger (z. B. alle mit dem "
                "passenden Recht), zusätzlich zu den ausgewählten Personen. Ohne beides bekommt "
                "sie niemand.",
                verbose_name="Wie vorgesehen",
            ),
        ),
        migrations.RunPython(vor, zurueck),
        migrations.RemoveField(model_name="mailempfaenger", name="niemand"),
    ]

# Mehrfachauswahl der Freigabe-Ziele (ADR 0063): aus den Einzel-Feldern ausgabestelle/fuer_person
# werden die Mehrfachfelder ausgabestellen/fuer_personen. Reihenfolge: erst die neuen Felder
# anlegen, dann die vorhandenen Werte übernehmen, erst danach die alten Felder entfernen – so
# geht keine gespeicherte Freigabe verloren.

from django.conf import settings
from django.db import migrations, models


def einzeln_in_mehrere(apps, schema_editor):
    EigeneListe = apps.get_model("listen", "EigeneListe")
    for e in EigeneListe.objects.all():
        if e.ausgabestelle_id:
            e.ausgabestellen.add(e.ausgabestelle_id)
        if e.fuer_person_id:
            e.fuer_personen.add(e.fuer_person_id)


def mehrere_in_einzeln(apps, schema_editor):
    # Rückweg (Downgrade): die erste Auswahl zurück in die Einzel-Felder; mehr passt dort nicht.
    EigeneListe = apps.get_model("listen", "EigeneListe")
    for e in EigeneListe.objects.all():
        stelle = e.ausgabestellen.first()
        person = e.fuer_personen.first()
        e.ausgabestelle_id = stelle.pk if stelle else None
        e.fuer_person_id = person.pk if person else None
        e.save(update_fields=["ausgabestelle", "fuer_person"])


class Migration(migrations.Migration):

    dependencies = [
        ("kunden", "0040_ausgabestelle_dienstplan_sichtbar"),
        ("listen", "0003_remove_eigeneliste_fuer_alle_and_more"),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.AddField(
            model_name="eigeneliste",
            name="ausgabestellen",
            field=models.ManyToManyField(
                blank=True,
                related_name="+",
                to="kunden.ausgabestelle",
                verbose_name="Ausgabestellen",
            ),
        ),
        migrations.AddField(
            model_name="eigeneliste",
            name="fuer_personen",
            field=models.ManyToManyField(
                blank=True,
                related_name="+",
                to=settings.AUTH_USER_MODEL,
                verbose_name="Personen",
            ),
        ),
        migrations.RunPython(einzeln_in_mehrere, mehrere_in_einzeln),
        migrations.RemoveField(
            model_name="eigeneliste",
            name="ausgabestelle",
        ),
        migrations.RemoveField(
            model_name="eigeneliste",
            name="fuer_person",
        ),
        migrations.AlterField(
            model_name="eigeneliste",
            name="sichtbarkeit",
            field=models.CharField(
                choices=[
                    ("privat", "Nur ich"),
                    ("stelle", "Bestimmte Ausgabestellen"),
                    ("alle_stellen", "Alle Ausgabestellen"),
                    ("person", "Bestimmte Personen"),
                    ("alle", "Alle"),
                ],
                default="privat",
                max_length=12,
                verbose_name="Sichtbar für",
            ),
        ),
    ]

"""Abholungen ohne Ausgabestelle bekommen die Ausgabestelle der heutigen Kundengruppe des
Haushalts. Ändert nur leere Felder und löscht nichts; Haushalte ohne Kundengruppe bleiben
„ohne Ausgabestelle“. Rückwärts bleibt der Stand (ein Leeren wäre ein Datenverlust)."""

from django.db import migrations
from django.db.models import OuterRef, Subquery


def zuordnen(apps, schema_editor):
    Abholung = apps.get_model("kunden", "Abholung")
    Haushalt = apps.get_model("kunden", "Haushalt")
    stelle = Haushalt.objects.filter(pk=OuterRef("haushalt_id")).values(
        "kundengruppe__ausgabestelle"
    )[:1]
    Abholung.objects.filter(
        ausgabestelle__isnull=True, haushalt__kundengruppe__ausgabestelle__isnull=False
    ).update(ausgabestelle=Subquery(stelle))


class Migration(migrations.Migration):
    dependencies = [("kunden", "0050_dokumentart_behindertenausweis")]

    operations = [migrations.RunPython(zuordnen, migrations.RunPython.noop)]

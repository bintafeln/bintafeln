from django.db import migrations
from django.db.models import OuterRef, Subquery


def nachfuellen(apps, schema_editor):
    """Bestehende Abholungen ohne Ausgabestelle aus der Kundengruppe des Haushalts nachfüllen.

    Beim Import ohne Ausgabestelle erbt eine Abholung sie seit ADR 0013-Fix von der
    Kundengruppe des Haushalts (die ihr eindeutig zugeordnet ist). Das griff aber nur für
    neu angelegte Abholungen; schon importierte blieben auf „–“. Diese einmalige Nachfüllung
    holt das nach. Nur dort, wo noch keine Ausgabestelle steht; Haushalte ohne Kundengruppe
    (z. B. ohne gültigen Ausweis, ADR 0061) bleiben leer, weil es nichts zu erben gibt.
    """
    Abholung = apps.get_model("kunden", "Abholung")
    Haushalt = apps.get_model("kunden", "Haushalt")
    stelle = Haushalt.objects.filter(pk=OuterRef("haushalt_id")).values(
        "kundengruppe__ausgabestelle"
    )[:1]
    (
        Abholung.objects.filter(
            ausgabestelle__isnull=True, haushalt__kundengruppe__isnull=False
        ).update(ausgabestelle=Subquery(stelle))
    )


class Migration(migrations.Migration):
    dependencies = [("kunden", "0046_ausweisvorlage_gruppe_termin_anhaengen")]

    # Rückwärts nichts tun: die nachgefüllte Ausgabestelle ist richtig und lässt sich nicht
    # von einer von Hand gesetzten unterscheiden.
    operations = [migrations.RunPython(nachfuellen, migrations.RunPython.noop)]

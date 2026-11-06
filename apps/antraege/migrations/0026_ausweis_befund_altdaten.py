"""Dokumentart (ADR 0112) für schon geprüfte Alt-Anträge nachtragen – soweit ohne erneutes Lesen
möglich: Ein Antrag mit erkanntem Ausweis (``ausweis_staat`` gesetzt) bekommt sofort „abweichung“
oder „passt“. Anträge ohne erkannten Ausweis bleiben ``befund=""`` und werden beim nächsten
„Alle Ausweise prüfen“ eingeordnet (dort entscheidet sich Amtsdokument/unklar per Texterkennung).
"""

from django.db import migrations


def altdaten_einordnen(apps, schema_editor):
    Antrag = apps.get_model("antraege", "Antrag")
    # Mit erkanntem Ausweis und Abweichung
    Antrag.objects.filter(
        ausweis_geprueft_am__isnull=False, ausweis_befund=""
    ).exclude(ausweis_staat="").filter(ausweis_abweichung=True).update(ausweis_befund="abweichung")
    # Mit erkanntem Ausweis, keine Abweichung
    Antrag.objects.filter(
        ausweis_geprueft_am__isnull=False, ausweis_befund="", ausweis_abweichung=False
    ).exclude(ausweis_staat="").update(ausweis_befund="passt")


def zurueck(apps, schema_editor):
    # Nur eine Einordnung; beim Zurückrollen nichts zu tun (das Feld entfernt die vorige Migration).
    pass


class Migration(migrations.Migration):
    dependencies = [("antraege", "0025_antrag_ausweis_befund")]

    operations = [migrations.RunPython(altdaten_einordnen, zurueck)]

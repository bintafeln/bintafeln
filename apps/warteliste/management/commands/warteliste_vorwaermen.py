"""Dubletten und Abgleich mit dem Kundenstamm vorrechnen (ADR 0109).

Läuft im App-Dienst alle 15 Minuten (siehe docker/entrypoint.sh), damit die Seiten „Doppelte
Anträge" und „Abgleich mit dem Kundenstamm" auch bei Inaktivität ohne Warten geöffnet werden
können. Rechnet nur, wenn das Ergebnis nicht aktuell ist und nicht schon eine Rechnung läuft.
"""

from django.core.management.base import BaseCommand


class Command(BaseCommand):
    help = "Warteliste: Dubletten und Abgleich im Hintergrund vorrechnen."

    def handle(self, *args, **options):
        from apps.core import module
        from apps.warteliste import vorberechnung

        if "warteliste" not in module.eingeschaltet():
            return  # Modul aus: nichts vorzurechnen
        vorberechnung.vorwaermen(synchron=True)

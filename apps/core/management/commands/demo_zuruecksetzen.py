from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from apps.core import demo


class Command(BaseCommand):
    help = (
        "Nur für eine öffentliche Demo (BINTAFELN_DEMO=true): löscht ALLE Daten und legt "
        "erfundene Beispieldaten und Demo-Konten an."
    )

    def handle(self, *args, **optionen):
        try:
            demo.zuruecksetzen()
        except ImproperlyConfigured as fehler:
            raise CommandError(str(fehler)) from fehler
        namen = ", ".join(name for name, *_ in demo.KONTEN)
        self.stdout.write(self.style.SUCCESS(f"Demo zurückgesetzt. Konten: {namen}"))

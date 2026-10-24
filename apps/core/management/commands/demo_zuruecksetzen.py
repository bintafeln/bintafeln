from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from apps.core import demo


class Command(BaseCommand):
    help = (
        "Nur für eine öffentliche Demo (BINTAFELN_DEMO=true): löscht ALLE Daten und legt "
        "erfundene Beispieldaten und Demo-Konten an."
    )

    def add_arguments(self, parser):
        parser.add_argument(
            "--auch-fremde-konten",
            action="store_true",
            help="Auch löschen, wenn es Konten gibt, die nicht mit demo- beginnen.",
        )

    def handle(self, *args, auch_fremde_konten=False, **optionen):
        try:
            demo.zuruecksetzen(erzwingen=auch_fremde_konten)
        except ImproperlyConfigured as fehler:
            raise CommandError(str(fehler)) from fehler
        namen = ", ".join(name for name, *_ in demo.KONTEN)
        self.stdout.write(self.style.SUCCESS(f"Demo zurückgesetzt. Konten: {namen}"))

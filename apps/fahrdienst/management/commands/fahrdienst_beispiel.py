"""Beispiel-Fahrerplan anlegen oder entfernen (apps/fahrdienst/beispiel.py)."""

from django.core.management.base import BaseCommand

from apps.fahrdienst import beispiel


class Command(BaseCommand):
    help = ("Legt Touren wie auf dem Papierplan und erfundene Fahrer/Beifahrer an und verteilt sie "
            "zufällig (nur zum Ausprobieren). Mit --entfernen wieder löschen.")  # fmt: skip

    def add_arguments(self, parser):
        parser.add_argument("--entfernen", action="store_true")

    def handle(self, *args, entfernen=False, **optionen):
        if entfernen:
            self.stdout.write(f"Erfundene Konten entfernt: {beispiel.entfernen()}")
            return
        for was, anzahl in beispiel.anlegen().items():
            self.stdout.write(f"{was}: {anzahl}")

"""Beispiel-Dienstplan anlegen oder entfernen (apps/dienstplan/beispiel.py)."""

from django.core.management.base import BaseCommand

from apps.dienstplan import beispiel


class Command(BaseCommand):
    help = ("Legt eine Beispiel-Ausgabestelle mit Mo/Mi/Fr, Aufgaben wie auf dem Papierplan "
            "und erfundenen Helfern an (zum Ausprobieren). --entfernen löscht sie.")  # fmt: skip

    def add_arguments(self, parser):
        parser.add_argument("--entfernen", action="store_true")

    def handle(self, *args, entfernen=False, **optionen):
        if entfernen:
            self.stdout.write(f"Erfundene Helfer entfernt: {beispiel.entfernen()}")
            return
        for was, anzahl in beispiel.anlegen().items():
            self.stdout.write(f"{was}: {anzahl}")

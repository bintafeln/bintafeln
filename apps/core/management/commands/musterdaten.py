"""Füllt eine Test-Installation mit erfundenen Musterdaten (apps/core/musterdaten.py)."""

from django.core.management.base import BaseCommand, CommandError

from apps.core import musterdaten


class Command(BaseCommand):
    help = (
        "Ersetzt Kundenstamm, Anträge, Adressen, Spenden und Mitglieder durch erfundene "
        "Musterdaten und legt Muster-Mitarbeitende an. Tafel-Einstellungen, Ausgabestellen, "
        "Antragsformular und eigene Konten bleiben. Nur für Test-Installationen!"
    )

    def add_arguments(self, parser):
        parser.add_argument("--ja", action="store_true",
                            help="Bestätigt, dass die genannten Daten ersetzt werden.")  # fmt: skip
        parser.add_argument("--passwort", default="",
                            help="Passwort der Muster-Konten (sonst zufällig).")  # fmt: skip
        parser.add_argument("--haushalte", type=int, default=150)

    def handle(self, *args, ja=False, passwort="", haushalte=150, **optionen):
        if not ja:
            raise CommandError(
                "Abbruch: Das ersetzt Kundenstamm, Anträge, Adressen, Spenden und Mitglieder "
                "vollständig. Vorher sichern (./betrieb sichern) und mit --ja bestätigen."
            )
        zaehler, passwort = musterdaten.erzeugen(passwort=passwort or None, haushalte=haushalte)
        for was, anzahl in zaehler.items():
            self.stdout.write(f"{was}: {anzahl}")
        self.stdout.write(f"Muster-Konten: {musterdaten.PRAEFIX}admin, {musterdaten.PRAEFIX}"
                          f"buero, … – Passwort für alle: {passwort}")  # fmt: skip

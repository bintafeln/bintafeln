"""Prüft die offenen Anträge auf Ausweise – als **eigener Prozess** (ADR 0107).

Der Treiber ``ausweis_scan.alle_pruefen_jetzt`` ruft diesen Befehl im Hintergrund auf, damit ein
Nachweis, der eine Bild-/PDF-Bibliothek abstürzen lässt oder endlos hängt, nur diesen Prozess
trifft und nicht den Webserver. Je Antrag gilt ein Zeitlimit (siehe ``stapel_im_prozess``).
"""

from django.core.management.base import BaseCommand

from apps.antraege import ausweis_scan


class Command(BaseCommand):
    help = "Prüft die offenen Anträge auf Ausweise (eigener Prozess, mit Zeitlimit je Antrag)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--zeit", type=int, default=ausweis_scan.ZEIT_JE_ANTRAG,
            help="Zeitlimit je Antrag in Sekunden.",
        )  # fmt: skip

    def handle(self, *args, **optionen):
        # Niedrige Priorität und optionaler Speicherdeckel (ADR 0111), damit die Bildprüfung den
        # Server nicht ausbremst oder überlastet.
        ausweis_scan.ressourcen_begrenzen()
        ausweis_scan.stapel_im_prozess(optionen["zeit"])

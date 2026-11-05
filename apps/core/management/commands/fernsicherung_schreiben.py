"""Schreibt die entschlüsselte rclone-Konfiguration für den Dienst „backup“ (ADR 0106).

Beim Start des Dienstes „app“ aufgerufen (entrypoint), damit der Dienst „backup“ die Fernablage
auch nach einem Neustart findet, ohne dass vorher in der Oberfläche gespeichert wurde.
"""

from django.core.management.base import BaseCommand

from apps.core import fernsicherung


class Command(BaseCommand):
    help = "Schreibt die rclone-Konfiguration der Fernsicherung für den Dienst backup."

    def handle(self, *args, **options):
        fernsicherung.schreiben()

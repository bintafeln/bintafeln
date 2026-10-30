"""Meldet die Tafel im bintafeln-Verzeichnis, wenn eingeschaltet und fällig (ADR 0089).

Läuft beim Webserver alle fünf Minuten mit (docker/entrypoint.sh); meldet aber nur nach einem
Update und sonst einmal pro Woche.
"""

from django.core.management.base import BaseCommand

from apps.core import verzeichnis


class Command(BaseCommand):
    help = "Meldet die Tafel im bintafeln-Verzeichnis, wenn eingeschaltet und fällig."

    def handle(self, *args, **optionen):
        if verzeichnis.bei_bedarf_melden():
            self.stdout.write("Im bintafeln-Verzeichnis gemeldet.")

"""Gesammelte Benachrichtigungen verschicken, die fällig sind (ADR 0086). Läuft im App-Container
alle fünf Minuten (docker/entrypoint.sh); von Hand: python manage.py benachrichtigungen_senden"""

from django.core.management.base import BaseCommand

from apps.core import benachrichtigung


class Command(BaseCommand):
    help = "Fällige gesammelte Benachrichtigungen per Mail verschicken."

    def handle(self, *args, **options):
        anzahl = benachrichtigung.senden()
        if anzahl:
            self.stdout.write(f"{anzahl} Mail(s) mit gesammelten Benachrichtigungen verschickt.")

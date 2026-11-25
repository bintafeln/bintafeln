"""Gesammelte Benachrichtigungen verschicken, die fällig sind (ADR 0086). Läuft im App-Container
alle fünf Minuten (docker/entrypoint.sh); von Hand: python manage.py benachrichtigungen_senden"""

from django.core.management.base import BaseCommand

from apps.core import benachrichtigung


class Command(BaseCommand):
    help = "Fällige gesammelte Benachrichtigungen per Mail verschicken."

    def handle(self, *args, **options):
        # Bei der Gelegenheit: Wird die Festplatte voll? Dann einmal je Stufe eine Mail (ADR 0169)
        from apps.core import speicherplatz

        speicherplatz.melden(speicherplatz.stand())
        # Vorgemerkte Glückwünsche zum Geburtstag, deren Uhrzeit erreicht ist (ADR 0179)
        from apps.konten import geburtstagsmail

        gruesse = geburtstagsmail.faellige_senden()
        if gruesse:
            self.stdout.write(f"{gruesse} vorgemerkte Glückwunsch-Mail(s) verschickt.")
        anzahl = benachrichtigung.senden()
        if anzahl:
            self.stdout.write(f"{anzahl} Mail(s) mit gesammelten Benachrichtigungen verschickt.")

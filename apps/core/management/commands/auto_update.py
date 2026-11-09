"""Prüft, ob ein automatisches Update fällig ist, und fordert es an (ADR 0043).

Läuft im Hintergrund alle fünf Minuten (docker/entrypoint.sh). Die eigentliche Regel steht in
``apps.core.update.auto_update_pruefen``; hier nur der Aufruf, damit cron/Hintergrundlauf sie
anstoßen können."""

from django.core.management.base import BaseCommand

from apps.core import update


class Command(BaseCommand):
    help = "Automatisches Update anstoßen, wenn eingeschaltet und fällig."

    def handle(self, *args, **options):
        version = update.auto_update_pruefen()
        if version:
            self.stdout.write(f"Automatisches Update auf {version} angefordert.")

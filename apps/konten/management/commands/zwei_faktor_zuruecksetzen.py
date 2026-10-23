from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from apps.konten import zwei_faktor


class Command(BaseCommand):
    help = (
        "Entfernt die Zwei-Faktor-Anmeldung eines Benutzers (App und Notfallcodes). "
        "Für den Notfall, wenn sich niemand mehr anmelden kann."
    )

    def add_arguments(self, parser):
        parser.add_argument("benutzername")

    def handle(self, *args, benutzername, **optionen):
        try:
            benutzer = get_user_model().objects.get(username=benutzername)
        except get_user_model().DoesNotExist as fehler:
            raise CommandError(f"Benutzer '{benutzername}' gibt es nicht.") from fehler
        zwei_faktor.abschalten(benutzer)
        self.stdout.write(
            self.style.SUCCESS(
                f"Zwei-Faktor für '{benutzername}' zurückgesetzt. Bei der nächsten Anmeldung "
                "muss es neu eingerichtet werden, falls es für die Rolle Pflicht ist."
            )
        )

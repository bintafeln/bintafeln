"""Prüfung von Passwörtern auf Leerzeichen.

Am iPad setzt die Tastatur nach einem Punkt oft von selbst ein Leerzeichen (aus „eins.zwei“ wird
„eins. zwei“). Im Passwortfeld sieht man das nicht – und später scheitert die Anmeldung, ohne dass
klar ist, warum. Deshalb werden Passwörter mit Leerzeichen gleich beim Festlegen abgelehnt, mit
einer verständlichen Meldung. Punkte und alle anderen Zeichen bleiben erlaubt.
"""

from django.core.exceptions import ValidationError

MELDUNG = ("Das Passwort enthält ein Leerzeichen (z. B. nach einem Punkt oder am Ende). Am iPad "
           "fügt die Tastatur das oft von selbst ein. Bitte ohne Leerzeichen eingeben – Punkte "
           "sind erlaubt.")  # fmt: skip


def leerzeichen_pruefen(passwort: str) -> None:
    if any(z.isspace() for z in passwort):
        raise ValidationError(MELDUNG, code="leerzeichen")


class KeineLeerzeichenValidator:
    """Für AUTH_PASSWORD_VALIDATORS: gilt für alle Passwörter von Personen."""

    def validate(self, password, user=None):
        leerzeichen_pruefen(password)

    def get_help_text(self):
        return "Das Passwort darf keine Leerzeichen enthalten."

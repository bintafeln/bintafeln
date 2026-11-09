"""Eigene Antwort bei fehlgeschlagener CSRF-Prüfung (ADR 0119).

Django bricht eine Anfrage mit ungültigem oder fehlendem CSRF-Token mit einer technischen
Sackgasse ab („Verboten (403) – CSRF-Verifizierung fehlgeschlagen“). Das passiert vor allem,
wenn eine Seite lange offen war (oder in einem zweiten Tab) und die Anmeldung inzwischen
abgelaufen ist: Das Formular trägt dann ein veraltetes Token. Bisher half nur, den Browser
ganz zu schließen.

Statt der Sackgasse schicken wir nicht angemeldete Besucher auf eine frische Anmeldeseite –
die bekommt ein neues Token, sodass die nächste Anmeldung sofort klappt. Angemeldete sehen
einen verständlichen Hinweis zum Neuladen.
"""

from django.contrib import messages
from django.shortcuts import redirect, render


def csrf_fehler(request, reason=""):
    """Wird über ``settings.CSRF_FAILURE_VIEW`` aufgerufen, wenn die CSRF-Prüfung scheitert."""
    if not request.user.is_authenticated:
        messages.info(request, "Die Seite war zu lange offen. Bitte melden Sie sich erneut an.")
        return redirect("konten:anmelden")
    return render(
        request,
        "403.html",
        {
            "exception": "Die Seite war zu lange offen. Bitte laden Sie sie neu und "
            "versuchen Sie es noch einmal."
        },  # fmt: skip
        status=403,
    )

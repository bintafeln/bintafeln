"""Übersicht „Wer bekommt welche Mail“ (ADR 0125): alle Mails an einer Stelle.

Benachrichtigungen an Mitarbeitende beschreibt ``apps.core.benachrichtigung.Art`` (wann, an wen,
bei Mails an eine Gruppe mit Auswahl der Empfänger). Alle übrigen Mails – an Kunden, Spender
oder einzelne Mitarbeitende – stehen hier (``KERN``) oder kommen von den Modulen
(``Modul.mails``). Sie werden nur erklärt; eingestellt werden sie dort, wohin der Link führt.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class Mail:
    titel: str
    wann: str
    an: str
    # Wo man sie einstellt: (Linktext, URL-Name, nötiges Recht) oder nichts
    wo: tuple[str, str, str] | None = None


KERN = (
    Mail("Zugang und Passwort",
         "Beim Anlegen eines Kontos, beim Zurücksetzen des Passworts und bei der Freigabe "
         "einer Registrierung.",
         "Die Person, um deren Konto es geht."),
    Mail("Eingangsbestätigung für einen Antrag",
         "Sobald jemand das Antragsformular abgeschickt und eine E-Mail-Adresse angegeben hat.",
         "Die antragstellende Person.",
         ("Anträge einstellen", "antraege:einstellungen", "einstellungen.antraege")),
    Mail("Dankesbrief und Spendenbestätigung",
         "Wenn jemand unter „Spenden → Dankesbriefe“ den Versand per Mail auslöst.",
         "Die Spenderin oder der Spender (Adresse aus dem Adressbuch).",
         ("Dankesbriefe", "spenden:dank", "spenden.bestaetigen")),
    Mail("Serienbrief per Mail",
         "Wenn jemand einen Serienbrief als Mail verschickt.",
         "Die für den Brief ausgewählten Personen.",
         ("Vorlagen", "serienbriefe:vorlagen", "serienbriefe.erstellen")),
    Mail("Liste als Mail (Export)",
         "Wenn jemand in einer Liste „per Mail senden“ wählt.",
         "Die Adresse, die dabei eingegeben wird."),
    Mail("Testmail",
         "Wenn jemand unter „E-Mail“ die Testmail auslöst.",
         "Die dabei angegebene Adresse.",
         ("E-Mail", "core:mail_einstellungen", "einstellungen.mail")),
)  # fmt: skip


def alle(darf: set[str]) -> list[dict]:
    """Alle weiteren Mails (Kern und eingeschaltete Module); der Link nur mit dem Recht."""
    from django.urls import reverse

    from apps.core import module

    mails = list(KERN)
    for m in module.alle():
        if module.aktiv(m.kennung):
            mails += m.mails
    return [
        {"mail": x, "link": reverse(x.wo[1]) if x.wo and x.wo[2] in darf else "",
         "linktext": x.wo[0] if x.wo else ""}
        for x in mails
    ]  # fmt: skip

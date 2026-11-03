"""CSV der tatsächlichen Aufruf-Reihenfolge eines Ausgabetags (ADR 0050).

Aus dem gespeicherten Tages-Stand (``AufrufTag.stand``) wird die Reihenfolge gebaut, in der die
Kundennummern an der Ausgabestelle aufgerufen/eingelassen wurden. Zurückgestellte Kunden
(„Spätzünder") sind mit Versatz, neuem Platz und Uhrzeit markiert. Es stehen ausschließlich
Kundennummern in der Datei, nie Namen.

Nach Abschluss des Tages verschickt ``bei_abschluss()`` die Datei einmal per Mail an die in den
Aufruf-Einstellungen hinterlegte Adresse (``AufrufEinstellungen.reihenfolge_mail``).
"""

import csv
import io
import logging

from apps.aufruf.ablauf import norm
from apps.aufruf.models import AufrufEinstellungen, AufrufTag
from apps.core import mail

logger = logging.getLogger(__name__)

KOPF = ["Reihenfolge", "Kundengruppe", "Kundennummer", "zurückgestellt", "Versatz",
        "neuer Platz", "Uhrzeit Zurückstellung"]  # fmt: skip


def zeilen(tag: AufrufTag) -> list[dict]:
    """Je aufgerufener/eingelassener Kundennummer eine Zeile, in der Reihenfolge des Tages."""
    s = tag.stand or {}
    spaet = {norm(k): v for k, v in (s.get("spaetzuender") or {}).items()}
    ergebnis = []
    pos = 0
    for g in s.get("gruppen", []):
        for nummer in list(g.get("eingelassen", [])) + list(g.get("aufgerufen", [])):
            pos += 1
            info = spaet.get(norm(nummer))
            ergebnis.append({
                "position": pos,
                "gruppe": g.get("name", ""),
                "nummer": nummer,
                "zurueckgestellt": bool(info),
                "versatz": (info or {}).get("versatz", ""),
                "neuer_platz": (info or {}).get("neuer_platz", ""),
                "zeit": (info or {}).get("zeit", ""),
            })  # fmt: skip
    return ergebnis


def csv_text(tag: AufrufTag) -> str:
    puffer = io.StringIO()
    puffer.write("﻿")  # BOM, damit Excel/LibreOffice Umlaute richtig lesen
    schreiber = csv.writer(puffer, delimiter=";")
    schreiber.writerow(KOPF)
    for z in zeilen(tag):
        schreiber.writerow([
            z["position"], z["gruppe"], z["nummer"],
            "ja" if z["zurueckgestellt"] else "",
            z["versatz"], z["neuer_platz"], z["zeit"],
        ])  # fmt: skip
    return puffer.getvalue()


def senden(stelle, datum, tag: AufrufTag | None = None, einstellungen=None) -> bool:
    """Schickt die Reihenfolge-CSV per Mail; True, wenn gesendet (Adresse gesetzt, Tag da)."""
    e = einstellungen or AufrufEinstellungen.laden(stelle)
    if not e.reihenfolge_mail:
        return False
    tag = tag or AufrufTag.objects.filter(ausgabestelle=stelle, datum=datum).first()
    if tag is None:
        return False
    basis = f"aufruf-reihenfolge-{stelle.name}-{datum:%Y-%m-%d}".replace(" ", "_")
    betreff = f"Aufruf-Reihenfolge {stelle.name} {datum:%d.%m.%Y}"
    text = (
        "Im Anhang die tatsächliche Reihenfolge, in der die Kundennummern heute aufgerufen "
        "wurden. Zurückgestellte Kunden sind mit „ja“, dem Versatz und der Uhrzeit markiert."
    )
    mail.senden(betreff, text, [e.reihenfolge_mail],
                anhaenge=[(f"{basis}.csv", csv_text(tag).encode("utf-8"), "text/csv")])  # fmt: skip
    return True


def bei_abschluss(tag: AufrufTag, einstellungen) -> None:
    """Einmal nach Abschluss des Tages die Reihenfolge-CSV verschicken (durch ein Flag im Stand
    gegen doppelten Versand gesichert). Fehler beim Mailversand brechen den Einlass nicht ab."""
    if not einstellungen.reihenfolge_mail or (tag.stand or {}).get("reihenfolge_gesendet"):
        return
    try:
        gesendet = senden(tag.ausgabestelle, tag.datum, tag=tag, einstellungen=einstellungen)
    except mail.MailFehler as fehler:
        logger.warning("Aufruf-Reihenfolge für %s nicht gesendet: %s", tag.ausgabestelle, fehler)
        return
    if gesendet:
        tag.stand["reihenfolge_gesendet"] = True
        tag.save(update_fields=["stand"])

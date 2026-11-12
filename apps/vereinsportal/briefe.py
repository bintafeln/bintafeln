"""Dankesbriefe zu den Belegen aus dem Vereinsportal (ADR 0126, Schritt 2).

Wie im bisherigen Spendenbelege-Programm: Einfachspender bekommen den Brief mit ihrem
Spendenbeleg, Mehrfachspender den Brief mit der im Vereinsportal erstellten und hier
hochgeladenen Sammelbescheinigung. Der Brief kommt aus einer Serienbrief-Vorlage. Wer per
E-Mail erreichbar ist, bekommt Brieftext und Anlagen als Mail, alle anderen ein Druck-PDF.
"""

import io
import re

from django.db import transaction
from django.utils import timezone
from pypdf import PdfReader, PdfWriter
from pypdf.errors import PdfReadError

from apps.core import privatdateien
from apps.serienbriefe import empfaenger as emp
from apps.serienbriefe import gestaltung
from apps.serienbriefe.brief import briefe_pdf
from apps.vereinsportal import auswertung
from apps.vereinsportal.einlesen import normal
from apps.vereinsportal.models import Beleg, Sammelbescheinigung


def auswahl(jahr: int, gruppe: str) -> list:
    """Spender einer Gruppe, für die noch ein Dankesbrief aussteht."""
    return [s for s in auswertung.spender(jahr) if s.gruppe == gruppe and s.unbedankt]


def bereit(s) -> bool:
    """Mehrfachspender brauchen die Sammelbescheinigung, sonst hätte der Brief keine Anlage."""
    return bool(s.sammel) if s.mehrfach else True


def werte(s, jahr: int) -> emp.Empfaenger:
    k = s.kontakt
    anrede = emp.briefanrede(k.anrede, k.vorname, k.nachname, False) if k else (
        "Sehr geehrte Damen und Herren,")  # fmt: skip
    return emp.Empfaenger(
        f"p:{normal(s.name)}", s.name, [s.name, s.strasse, s.plz_ort], s.email,
        {"anrede": anrede, "name": s.name, "vorname": k.vorname if k else "",
         "nachname": k.nachname if k else "", "spendensumme": emp._euro(s.summe),
         "anzahl_spenden": s.anzahl, "spendendaten": s.spendendaten},
    )  # fmt: skip


def dateiname(name: str) -> str:
    name = re.sub(r"[^\w.\-]+", "_", name).strip("._") or "Beleg"
    return name if name.lower().endswith(".pdf") else f"{name}.pdf"


def anlagen(s) -> list[tuple[str, bytes]]:
    """PDF-Anlagen als (Dateiname, Inhalt): Sammelbescheinigung oder die offenen Belege."""
    if s.mehrfach:
        quellen = [(Sammelbescheinigung.ORDNER, s.sammel)] if s.sammel else []
    else:
        quellen = [(Beleg.ORDNER, b) for b in s.unbedankt]
    liste = []
    for ordner, eintrag in quellen:
        inhalt = privatdateien.lesen(ordner, eintrag.datei)
        if inhalt:
            liste.append((dateiname(eintrag.dateiname), inhalt))
    return liste


def _anhaengen(schreiber: PdfWriter, inhalt: bytes) -> bool:
    try:
        schreiber.append(PdfReader(io.BytesIO(inhalt)))
    except (PdfReadError, ValueError, OSError):
        return False
    return True


def druck_pdf(liste: list, vorlage, jahr: int, allgemein: dict) -> tuple[bytes, list[str]]:
    """Ein PDF: je Spender Brief und Anlagen hintereinander. Liefert (PDF, Warnungen)."""
    schreiber, warnungen = PdfWriter(), []
    for s in liste:
        e = werte(s, jahr)
        _anhaengen(schreiber, briefe_pdf([(e.anschrift, *gestaltung.brief(vorlage, e, allgemein))],
                                         vorlage))  # fmt: skip
        for name, inhalt in anlagen(s):
            if not _anhaengen(schreiber, inhalt):
                warnungen.append(f"{s.name}: „{name}“ ist kein lesbares PDF.")
    puffer = io.BytesIO()
    schreiber.write(puffer)
    return puffer.getvalue(), warnungen


def vermerken(liste: list, per: str) -> None:
    Beleg.objects.filter(pk__in=[b.pk for s in liste for b in s.unbedankt]).update(
        bedankt_am=timezone.localdate(), bedankt_per=per
    )


# --- Sammelbescheinigungen ---------------------------------------------------------------------


def zuordnen(datei: str, namen: list[str]) -> str:
    """Spendername, dessen Wörter alle im Dateinamen stehen; bei mehreren der längste Name."""
    stamm = normal(re.sub(r"[_\-]+", " ", datei.rsplit(".", 1)[0]))
    bester, woerter = "", 0
    for name in namen:
        teile = normal(name).split()
        if teile and len(teile) > woerter and all(t in stamm for t in teile):
            bester, woerter = name, len(teile)
    return bester


def mehrfachspender(jahr: int) -> list[str]:
    return [s.name for s in auswertung.spender(jahr) if s.mehrfach]


@transaction.atomic
def zuweisen(sammel: Sammelbescheinigung, name: str) -> None:
    """Ordnet zu; eine ältere Sammelbescheinigung desselben Spenders und Jahres wird ersetzt."""
    alt = Sammelbescheinigung.objects.filter(jahr=sammel.jahr, such_name=normal(name))
    for vorher in alt.exclude(pk=sammel.pk):
        privatdateien.loeschen(Sammelbescheinigung.ORDNER, vorher.datei)
        vorher.delete()
    sammel.name, sammel.such_name = name[:250], normal(name)[:250]
    sammel.save()


def hochladen(datei, jahr: int, von: str) -> Sammelbescheinigung:
    """Speichert das PDF verschlüsselt und ordnet es über den Dateinamen zu, wenn möglich."""
    ablage = privatdateien.speichern(Sammelbescheinigung.ORDNER, datei,
                                     typen=("application/pdf",), max_mb=10)  # fmt: skip
    sammel = Sammelbescheinigung(jahr=jahr, dateiname=datei.name[:200], datei=ablage,
                                 hochgeladen_von=von)  # fmt: skip
    name = zuordnen(datei.name, mehrfachspender(jahr))
    if name:
        zuweisen(sammel, name)
    else:
        sammel.save()
    return sammel

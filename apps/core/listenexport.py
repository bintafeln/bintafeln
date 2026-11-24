"""Listen ausliefern: dieselbe Liste als CSV, als PDF oder per E-Mail (ADR 0096).

Jede Übersichtsliste baut ihren CSV-Text wie bisher und reicht ihn an ``ausliefern()``. Je nach
Knopf (``aktion``) kommt die CSV-Datei (wie gehabt), ein PDF oder eine E-Mail mit beidem im Anhang
heraus – praktisch für Tablets, auf denen sich CSV nicht öffnen lässt.
"""

import csv
import io

from django.contrib import messages
from django.http import HttpResponse
from django.shortcuts import redirect
from reportlab.lib.pagesizes import A4, landscape
from reportlab.platypus import Spacer

from apps.core import mail
from apps.core.pdf import Pdf, pdf_antwort


def _zeilen(csv_text: str) -> tuple[list[str], list[list[str]]]:
    """CSV (Semikolon) in Kopfzeile und Datenzeilen zerlegen; BOM vorne entfernen."""
    leser = csv.reader(io.StringIO(csv_text.lstrip("﻿")), delimiter=";")
    zeilen = [z for z in leser if z]
    return (zeilen[0], zeilen[1:]) if zeilen else ([], [])


MAX_LEERSPALTEN = 2
LEER_ANTEIL = 0.2  # so viel der Blattbreite bekommt jede Leerspalte
MIN_ANTEIL = 0.035  # schmaler wird keine Spalte neben Leerspalten


def leerspalten(request) -> list[str]:
    """Die gewünschten Leerspalten fürs PDF (zum Eintragen oder Unterschreiben): Anzahl aus
    ``leer`` (0 bis 2), Überschriften aus ``leer_titel`` (mit Komma getrennt, dürfen fehlen)."""
    try:
        anzahl = int(request.GET.get("leer") or 0)
    except ValueError:
        anzahl = 0
    anzahl = max(0, min(anzahl, MAX_LEERSPALTEN))
    titel = [t.strip()[:40] for t in (request.GET.get("leer_titel") or "").split(",")]
    return [(titel[i] if i < len(titel) else "") for i in range(anzahl)]


def mit_leerspalten(kopf: list, zeilen: list[list], leer) -> tuple[list, list[list], list | None]:
    """Hängt die Leerspalten rechts an. Liefert Kopf, Zeilen und die Spaltenbreiten (Anteile der
    Blattbreite): jede Leerspalte bekommt festen Platz, der Rest teilt sich nach der Länge des
    Inhalts auf. Ohne Leerspalten bleibt alles, wie es ist (Breiten ``None``)."""
    leer = list(leer)[:MAX_LEERSPALTEN]
    if not leer or not kopf:
        return kopf, zeilen, None
    gewicht = []
    for i, name in enumerate(kopf):
        laengste = max([len(str(name))] + [len(str(z[i])) for z in zeilen if i < len(z)])
        gewicht.append(max(7, min(laengste + 2, 28)))
    # Bei sehr vielen Spalten werden die Leerspalten schmaler, und keine Spalte fällt unter die
    # Mindestbreite – sonst passt nicht einmal mehr ein Buchstabe hinein
    anteil = min(LEER_ANTEIL, 1 / (len(kopf) / 3 + len(leer)))
    rest = 1 - anteil * len(leer)
    roh = [max(rest * g / sum(gewicht), MIN_ANTEIL) for g in gewicht]
    breiten = [rest * b / sum(roh) for b in roh] + [anteil] * len(leer)
    # wirklich leer: ein leerer Text bekäme im PDF den Strich „–“
    return [*kopf, *leer], [[*z, *[Spacer(1, 1) for _ in leer]] for z in zeilen], breiten


def pdf_aus_csv(titel: str, csv_text: str, ohne_spalten=(), reihenfolge=(), leer=()) -> bytes:
    """Die Liste als PDF-Tabelle (quer, damit viele Spalten passen). ``ohne_spalten``: Spalten
    (Überschriften der CSV), die im PDF fehlen sollen – das sind die, die die Person in der Liste
    ausgeblendet hat. Die CSV-Datei behält immer alle Spalten. ``leer``: Überschriften von
    Leerspalten, die rechts angehängt werden (nur im PDF)."""
    kopf, zeilen = _zeilen(csv_text)
    bleiben = [i for i, name in enumerate(kopf) if name not in set(ohne_spalten)]
    if bleiben and len(bleiben) < len(kopf):
        kopf = [kopf[i] for i in bleiben]
        zeilen = [[z[i] if i < len(z) else "" for i in bleiben] for z in zeilen]
    if reihenfolge:
        # Spalten in der Reihenfolge, die die Person in der Liste gewählt hat; der Rest dahinter
        rang = {name: i for i, name in enumerate(reihenfolge)}
        folge = sorted(range(len(kopf)), key=lambda i: rang.get(kopf[i], len(rang)))
        kopf = [kopf[i] for i in folge]
        zeilen = [[z[i] if i < len(z) else "" for i in folge] for z in zeilen]
    doc = Pdf(titel, seitengroesse=landscape(A4))
    if leer and zeilen:
        kopf, zeilen = list(kopf), [[z[i] if i < len(z) else "" for i in range(len(kopf))]
                                    for z in zeilen]  # fmt: skip
        kopf, zeilen, breiten = mit_leerspalten(kopf, zeilen, leer)
        doc.tabelle(kopf, zeilen, breiten=breiten, gitter=True, luft=True)
    else:
        doc.tabelle(kopf, zeilen)
    return doc.erzeugen()


def _mailen(titel: str, basisname: str, csv_text: str, ziel: str, ohne_spalten=(),
            reihenfolge=(), leer=()) -> None:  # fmt: skip
    pdf = pdf_aus_csv(titel, csv_text, ohne_spalten, reihenfolge, leer)
    anhaenge = [
        (f"{basisname}.pdf", pdf, "application/pdf"),
        (f"{basisname}.csv", csv_text.encode("utf-8"), "text/csv"),
    ]
    mail.senden(
        f"{titel} aus bintafeln",
        f"Im Anhang die Liste „{titel}“ als PDF und als CSV-Datei (für Excel/LibreOffice).",
        [ziel],
        anhaenge=anhaenge,
        art="export",
    )


def ausliefern(request, titel: str, basisname: str, csv_text: str, weiter: str = "/",
               ohne_spalten=(), reihenfolge=()):  # fmt: skip
    """CSV-, PDF- oder E-Mail-Antwort je nach ``aktion`` (alle über das Auswahl-Formular, GET).
    CSV ist die Vorgabe und verhält sich wie der bisherige Export; „mail“ sendet und leitet
    mit Meldung auf die Liste zurück."""
    aktion = request.GET.get("aktion") or "csv"
    leer = leerspalten(request)  # nur im PDF; die CSV bleibt, wie sie ist
    if aktion == "pdf":
        return pdf_antwort(pdf_aus_csv(titel, csv_text, ohne_spalten, reihenfolge, leer),
                           f"{basisname}.pdf")  # fmt: skip
    if aktion == "mail":
        ziel = (request.GET.get("email") or "").strip()
        wohin = request.GET.get("weiter") or weiter
        if not wohin.startswith("/"):
            wohin = weiter
        if not ziel:
            messages.error(request, "Bitte eine E-Mail-Adresse angeben.")
        else:
            try:
                _mailen(titel, basisname, csv_text, ziel, ohne_spalten, reihenfolge, leer)
                messages.success(request, f"Die Liste wurde an {ziel} gesendet.")
            except mail.MailFehler as fehler:
                messages.error(request, f"E-Mail nicht gesendet: {fehler}")
        return redirect(wohin)
    antwort = HttpResponse(csv_text, content_type="text/csv; charset=utf-8")
    antwort["Content-Disposition"] = f'attachment; filename="{basisname}.csv"'
    return antwort

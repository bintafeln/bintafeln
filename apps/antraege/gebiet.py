"""Einzugsgebiet der Tafel: passt die Anschrift eines Antrags (PLZ, Ort)?

Geprüft wird nur gegen die eingestellten Postleitzahlen und Orte, nicht, ob es die Anschrift
wirklich gibt; das ginge nur mit einem fremden Dienst, an den Anschriften nicht gehen sollen.
"""

import re

from apps.antraege.models import AntragEinstellungen

Pruefung = AntragEinstellungen.Gebiet


def plz_bereiche(text: str) -> list[tuple[int, int]]:
    """„45127-45359, 45899“ → [(45127, 45359), (45899, 45899)]; Unlesbares wird übergangen."""
    bereiche = []
    for teil in re.split(r"[,;\s]+", text.replace("–", "-")):
        von, _, bis = teil.partition("-")
        if von.isdigit() and (not bis or bis.isdigit()):
            a, b = int(von), int(bis or von)
            bereiche.append((min(a, b), max(a, b)))
    return bereiche


def orte(text: str) -> list[str]:
    return [o for o in (_ort(t) for t in re.split(r"[,;\n]+", text)) if o]


def _ort(text: str) -> str:
    return " ".join(text.split()).casefold()


def _ort_passt(ort: str, erlaubt: list[str]) -> bool:
    # „Essen-Steele“ oder „Essen (Ruhr)“ gehört zu „Essen“
    ort = _ort(ort)
    return any(ort == o or ort.startswith((f"{o}-", f"{o} ", f"{o}(")) for o in erlaubt)


def _plz_passt(plz: str, bereiche: list[tuple[int, int]]) -> bool:
    ziffern = (plz or "").strip()
    return ziffern.isdigit() and any(a <= int(ziffern) <= b for a, b in bereiche)


def passt(e: AntragEinstellungen, plz: str, ort: str) -> bool | None:
    """True/False, ob die Anschrift im Gebiet liegt; None, wenn nichts zu prüfen ist.

    Jede eingetragene Liste muss passen: mit PLZ und Orten also beides.
    """
    if e.gebiet_pruefen == Pruefung.AUS or not (plz or ort):
        return None
    bereiche, erlaubt = plz_bereiche(e.gebiet_plz), orte(e.gebiet_orte)
    if not bereiche and not erlaubt:
        return None
    if bereiche and not _plz_passt(plz, bereiche):
        return False
    return not erlaubt or _ort_passt(ort or "", erlaubt)


def ausserhalb(e: AntragEinstellungen, antrag) -> bool:
    return passt(e, antrag.plz, antrag.ort) is False


def grund(e: AntragEinstellungen, antrag) -> str:
    """Kurzer Grund für die Markierung – nennt, *was* außerhalb liegt (PLZ, Ort oder beides).

    So sieht man nach dem Korrigieren der PLZ sofort, ob noch der Ort das Problem ist. Leer,
    wenn die Anschrift passt oder nicht geprüft wird.
    """
    if passt(e, antrag.plz, antrag.ort) is not False:
        return ""
    bereiche, erlaubt = plz_bereiche(e.gebiet_plz), orte(e.gebiet_orte)
    plz_schlecht = bool(bereiche) and not _plz_passt(antrag.plz, bereiche)
    ort_schlecht = bool(erlaubt) and not _ort_passt(antrag.ort or "", erlaubt)
    if plz_schlecht and ort_schlecht:
        return "PLZ und Ort außerhalb des Gebiets"
    if plz_schlecht:
        return "PLZ außerhalb des Gebiets"
    return "Ort außerhalb des Gebiets"


def name(e: AntragEinstellungen) -> str:
    """Name des Gebiets für die Meldung im Formular."""
    return (
        e.gebiet_name.strip()
        or ", ".join(o.strip() for o in re.split(r"[,;\n]+", e.gebiet_orte) if o.strip())
        or e.gebiet_plz.strip()
    )

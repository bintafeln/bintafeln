"""Aus der Anschriftzeile eines Belegs eine Adresse fürs Adressbuch machen (ADR 0128).

Auf dem Beleg steht der Spender als ein Stück („Erika Beispiel“, „Bäckerei Probe GmbH“). Reine
Funktionen ohne Datenbank, damit auch die Datenmigration sie nutzen kann.
"""

import re

# Woran man eine Organisation erkennt; alles andere gilt als Person
ORGANISATION = re.compile(
    r"&|\b(gmbh|mbh|ag|kg|ohg|ug|gbr|e\.\s?v\.?|ev|e\.\s?k\.?|stiftung|verein|vereinigung|firma|"
    r"co\.?|gemeinde|kirche|kirchengemeinde|pfarrei|schule|kita|apotheke|praxis|gesellschaft|"
    r"bank|sparkasse|club|lions|rotary|werk|genossenschaft|eg|bäckerei|metzgerei|markt)\b",
    re.IGNORECASE,
)
PLZ_ORT = re.compile(r"^\s*(\d{4,5})\s+(.+?)\s*$")


def normal(name: str) -> str:
    """Name zum Vergleichen: klein geschrieben, einfache Leerzeichen."""
    return " ".join((name or "").strip().lower().split())


def teile(name: str) -> dict:
    """Felder der Adresse: Organisation, oder Person mit dem letzten Wort als Nachname."""
    name = " ".join((name or "").split())
    if ORGANISATION.search(name):
        return {"art": "organisation", "organisation": name[:200], "vorname": "", "nachname": ""}
    *vorn, nachname = name.split() or [""]
    return {"art": "person", "organisation": "", "vorname": " ".join(vorn)[:100],
            "nachname": nachname[:100]}  # fmt: skip


def plz_ort(text: str) -> tuple[str, str]:
    """„54321 Beispieldorf“ -> („54321“, „Beispieldorf“); ohne PLZ steht alles im Ort."""
    treffer = PLZ_ORT.match(text or "")
    return (treffer.group(1), treffer.group(2)[:100]) if treffer else ("", (text or "")[:100])


def schluessel(name: str, plz: str) -> str:
    """Woran eine vorhandene Adresse wiedererkannt wird: Name und PLZ."""
    return f"{normal(name)}|{(plz or '').strip()}"

"""Einlesen von Werten im Format von docs/importformat.md."""

import datetime as dt

JA = {"ja", "j", "1", "wahr", "true", "x"}
NEIN = {"nein", "n", "0", "falsch", "false", ""}


class UngueltigerWert(ValueError):
    pass


def ja_nein(text: str) -> bool:
    wert = (text or "").strip().lower()
    if wert in JA:
        return True
    if wert in NEIN:
        return False
    raise UngueltigerWert(f"kein Ja/Nein-Wert: {text!r}")


def datum(text: str) -> dt.date | None:
    """Liest TT.MM.JJJJ oder JJJJ-MM-TT; leer ergibt None."""
    wert = (text or "").strip()
    if not wert:
        return None
    for muster in ("%d.%m.%Y", "%Y-%m-%d"):
        try:
            return dt.datetime.strptime(wert, muster).date()
        except ValueError:
            continue
    raise UngueltigerWert(f"kein Datum: {text!r}")

"""Eigene Texte des Antragsformulars mit KI übersetzen (ADR 0082).

Auf Knopfdruck gehen die deutschen Texte der Tafel (Überschrift, Einleitung, Hinweis zu den
Nachweisen, Seite nach dem Absenden, Antwortmail) an Claude (Anthropic) und kommen übersetzt
als Texte der jeweiligen Sprache zurück. Nur diese Texte verlassen den Server, nie Angaben aus
Anträgen. Nötig ist ein eigener API-Schlüssel der Tafel (verschlüsselt gespeichert, ADR 0016).
"""

import json
import re

from apps.antraege import sprachen
from apps.antraege.models import AntragEinstellungen, AntragText
from apps.core import geheimnis

MODELL = "claude-opus-5-5"
FELDER = ["kopf", "ueberschrift", "einleitung", "anhaenge_hinweis", "bestaetigung",
          "mail_betreff", "mail_text", "fuss"]  # fmt: skip
PLATZHALTER = re.compile(r"\{\w+\}")
ANWEISUNG = (
    "Du übersetzt die Texte einer Tafel (Lebensmittelausgabe für Menschen mit wenig Geld) für "
    "ihr Online-Antragsformular aus dem Deutschen in die Sprache {sprache}. Schreibe einfach, "
    "freundlich und respektvoll, in der höflichen Anrede der Zielsprache. Übersetze nur den "
    "sichtbaren Text: HTML-Elemente, Attribute, Links, E-Mail-Adressen, Telefonnummern, Namen "
    "der Tafel und Platzhalter in geschweiften Klammern wie {{nummer}} bleiben genau so stehen. "
    "Gib für jeden Eintrag die Übersetzung unter demselben Schlüssel zurück."
)


class UebersetzungsFehler(Exception):
    """Verständliche Meldung für die Oberfläche."""


def _schluessel() -> str:
    return geheimnis.entschluesseln(AntragEinstellungen.laden().ki_schluessel_verschluesselt)


def verfuegbar() -> bool:
    return bool(_schluessel())


def _client():
    import anthropic

    return anthropic.Anthropic(api_key=_schluessel(), max_retries=3, timeout=240)


def deutsche_texte() -> dict[str, str]:
    """Die eigenen deutschen Texte, die übersetzt werden (leere fallen weg)."""
    de = AntragText.objects.filter(sprache="de").first()
    return {f: getattr(de, f) for f in FELDER if de and getattr(de, f).strip()}


def uebersetzen(texte: dict[str, str], code: str) -> dict[str, str]:
    """Übersetzt ``texte`` (Feld → deutscher Text) in die Sprache ``code``."""
    import anthropic

    s = sprachen.sprache(code)
    schema = {"type": "object", "properties": {f: {"type": "string"} for f in texte},
              "required": list(texte), "additionalProperties": False}  # fmt: skip
    try:
        antwort = _client().beta.messages.create(
            model=MODELL,
            max_tokens=16000,
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",  # lehnt das Modell ab, übernimmt ein anderes
            output_config={"effort": "low", "format": {"type": "json_schema", "schema": schema}},
            system=ANWEISUNG.format(sprache=f"{s.deutsch} ({s.name})"),
            messages=[{"role": "user", "content": json.dumps(texte, ensure_ascii=False)}],
        )
    except anthropic.AuthenticationError as e:
        raise UebersetzungsFehler("Der API-Schlüssel wird nicht angenommen.") from e
    except anthropic.RateLimitError as e:
        raise UebersetzungsFehler("Zu viele Anfragen; bitte später noch einmal.") from e
    except anthropic.APIConnectionError as e:
        raise UebersetzungsFehler("Keine Verbindung zum Übersetzungsdienst.") from e
    except anthropic.APIStatusError as e:
        meldung = f"Der Übersetzungsdienst meldet einen Fehler ({e.status_code})."
        raise UebersetzungsFehler(meldung) from e
    if antwort.stop_reason != "end_turn":
        raise UebersetzungsFehler("Die Übersetzung wurde nicht vollständig geliefert.")
    text = next((b.text for b in antwort.content if b.type == "text"), "")
    try:
        ergebnis = json.loads(text)
    except ValueError as e:
        raise UebersetzungsFehler("Die Antwort ließ sich nicht lesen.") from e
    # Nur übernehmen, was vollständig ist und dieselben Platzhalter enthält
    return {
        f: ergebnis[f].strip()
        for f in texte
        if isinstance(ergebnis.get(f), str)
        and ergebnis[f].strip()
        and set(PLATZHALTER.findall(ergebnis[f])) == set(PLATZHALTER.findall(texte[f]))
    }


def sprache_uebersetzen(code: str) -> int:
    """Übersetzt die deutschen Texte in ``code`` und speichert sie dort; überschreibt nur die
    übersetzten Felder. Liefert die Zahl der übernommenen Texte."""
    texte = deutsche_texte()
    if not texte or code == "de":
        return 0
    neu = uebersetzen(texte, code)
    ziel = AntragText.objects.filter(sprache=code).first() or AntragText(sprache=code)
    for feld, wert in neu.items():
        setattr(ziel, feld, wert)
    ziel.save()
    return len(neu)


def sprachen_ohne_deutsch() -> list:
    return [s for s in sprachen.SPRACHEN if s.code != "de"]

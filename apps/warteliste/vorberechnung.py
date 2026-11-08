"""Vorberechnung von „Doppelte Anträge" und „Abgleich mit dem Kundenstamm" (ADR 0109).

Beide Auswertungen sind teuer: Dubletten vergleichen jeden offenen Antrag mit jedem, der Abgleich
sucht je Antrag über den Trigramm-Index ähnliche Haushalte im ganzen Kundenstamm. Bisher lief die
Rechnung erst beim Öffnen der Seite – man wartete 10–20 s.

Hier wird das **Ergebnis** im gemeinsamen Datenbank-Cache (ADR 0093) gehalten und bei Bedarf im
**Hintergrund** aufgefrischt:

* Ist das Ergebnis zum aktuellen Stand (``signatur``) vorhanden, kommt es sofort aus dem Cache –
  die Seite ist ohne Warten da.
* Ist noch gar keins da (erstes Mal, oder nach einer Entscheidung, die den Cache verwirft), wird
  einmal gerechnet und gespeichert; danach ist es warm.
* Hat sich etwas geändert (neue Anträge, Kundenstamm), zeigt die Seite sofort das **zuletzt**
  berechnete Ergebnis und frischt es **im Hintergrund** auf; neue Anträge kommen so von selbst
  dazu, ohne dass jemand darauf wartet.

Der Cache liegt in der Datenbank und überlebt einen Neustart (Update) – die Seiten bleiben also
auch danach sofort da. Gespeichert werden render-fertige einfache Daten (keine Modell-Objekte),
damit die Templates unverändert bleiben und der Cache stabil ist.
"""

import logging
import threading
import time

from django.core.cache import cache
from django.core.exceptions import ObjectDoesNotExist
from django.db import connections
from django.db.models import Count, Max

log = logging.getLogger(__name__)

DUB = "warteliste_dubletten"
ABG = "warteliste_abgleich"
DAUER = 86400  # 1 Tag im Cache
# Eine Hintergrund-Auffrischung ohne Lebenszeichen gilt nach so vielen Sekunden als abgebrochen
# (z. B. durch einen Neustart); die nächste Anfrage darf dann neu anstoßen.
VERWAIST = 300


# ── Hintergrund-Gerüst ───────────────────────────────────────────────────────


def _im_hintergrund(fn) -> None:
    """``fn`` in einem Daemon-Thread laufen lassen; dessen DB-Verbindung danach schließen.
    (In Tests ersetzt, um synchron zu rechnen.)"""

    def lauf():
        try:
            fn()
        except Exception as fehler:  # noqa: BLE001 – nur eine Auffrischung, darf nie stören
            log.warning("Vorberechnung im Hintergrund fehlgeschlagen: %s", fehler)
        finally:
            connections.close_all()

    threading.Thread(target=lauf, daemon=True).start()


def _laeuft(key) -> bool:
    stand = cache.get(key)
    return bool(
        stand and stand.get("laeuft") and time.time() - stand.get("aktualisiert", 0) <= VERWAIST
    )


def _rechnen_speichern(key, sig_fn, rechnen):
    """Synchron rechnen und mit der aktuellen Signatur im Cache ablegen."""
    sig = sig_fn()
    daten = rechnen()
    cache.set(
        key,
        {"signatur": sig, "daten": daten, "laeuft": False, "aktualisiert": time.time()},
        DAUER,
    )
    return daten


def _auffrischen(key, sig_fn, rechnen) -> None:
    """Im Hintergrund neu rechnen, falls nicht schon eine Auffrischung läuft."""
    if _laeuft(key):
        return
    stand = dict(cache.get(key) or {})
    stand["laeuft"] = True
    stand["aktualisiert"] = time.time()
    cache.set(key, stand, DAUER)
    _im_hintergrund(lambda: _rechnen_speichern(key, sig_fn, rechnen))


def _holen(key, sig_fn, rechnen):
    """(daten, frisch, laeuft). Sofort aus dem Cache; nie synchron blockieren.

    * Cache passt zum Stand → (daten, True, …).
    * Veraltet, aber brauchbar → zuletzt berechnetes Ergebnis sofort zeigen und im Hintergrund
      auffrischen → (alte_daten, False, läuft?).
    * Noch gar nichts berechnet → im Hintergrund anstoßen und ``daten=None`` liefern (die Seite
      zeigt „wird vorbereitet“ und lädt sich nach). ``None`` heißt „noch nicht da“, ``[]`` heißt
      „gerechnet, keine Treffer“.
    """
    sig = sig_fn()
    stand = cache.get(key)
    if stand and stand.get("signatur") == sig and "daten" in stand:
        return stand["daten"], True, _laeuft(key)
    hatte = stand.get("daten") if stand else None
    _auffrischen(key, sig_fn, rechnen)
    if hatte is not None:
        return hatte, False, _laeuft(key)  # veraltet, aber brauchbar
    # Erstmalig: in Tests rechnet _auffrischen synchron, dann ist das Ergebnis schon da.
    neu = cache.get(key)
    if neu and "daten" in neu and neu.get("signatur") == sig:
        return neu["daten"], True, False
    return None, False, True  # wird gerade erstmalig im Hintergrund vorbereitet


def vorwaermen() -> None:
    """Dubletten und Abgleich im Hintergrund vorberechnen, sobald man den Warteliste-Bereich
    betritt – dann ist die jeweilige Seite beim Öffnen meist schon fertig. Ist das Ergebnis aktuell
    oder läuft bereits eine Rechnung, passiert nichts."""
    for key, sig_fn, rechnen in (
        (DUB, _sig_dubletten, _rechnen_dubletten),
        (ABG, _sig_abgleich, _rechnen_abgleich),
    ):
        stand = cache.get(key)
        aktuell = stand and stand.get("signatur") == sig_fn() and "daten" in stand
        if not aktuell:
            _auffrischen(key, sig_fn, rechnen)


def veraltet(*, dubletten: bool = False, abgleich: bool = False) -> None:
    """Das zwischengespeicherte Ergebnis verwerfen (nach einer Entscheidung/Streichung), damit die
    nächste Anfrage frisch rechnet."""
    if dubletten:
        cache.delete(DUB)
    if abgleich:
        cache.delete(ABG)


# ── Signaturen (ändert sich eine, wird neu gerechnet) ────────────────────────


def _ts(d) -> float:
    return d.timestamp() if d else 0.0


def _offene():
    from apps.antraege.models import Antrag
    from apps.warteliste.models import Wartestand

    return Antrag.objects.exclude(wartestand__status__in=Wartestand.ABGESCHLOSSEN).filter(
        status__in=Antrag.OFFEN
    )


def _sig_dubletten():
    from apps.warteliste.models import DubletteIgnoriert, Wartestand

    a = _offene().aggregate(n=Count("pk"), m=Max("pk"))
    letzte = Wartestand.objects.aggregate(t=Max("geaendert_am"))["t"]
    return ("dub", a["n"], a["m"] or 0, DubletteIgnoriert.objects.count(), _ts(letzte))


def _sig_abgleich():
    from apps.kunden.models import Haushalt
    from apps.warteliste.models import AbgleichEntscheidung, Wartestand

    a = _offene().aggregate(n=Count("pk"), m=Max("pk"))
    letzte = Wartestand.objects.aggregate(t=Max("geaendert_am"))["t"]
    h = Haushalt.objects.aggregate(n=Count("pk"), t=Max("geaendert_am"))
    return (
        "abg", a["n"], a["m"] or 0, _ts(letzte),
        AbgleichEntscheidung.objects.count(), h["n"], _ts(h["t"]),
    )  # fmt: skip


# ── Rechnen und in render-fertige einfache Daten umwandeln ────────────────────


def _antrag_dict(a) -> dict:
    return {
        "pk": a.pk, "nummer": a.nummer, "eingegangen_am": a.eingegangen_am,
        "nachname": a.nachname, "vorname": a.vorname, "geburtsdatum": a.geburtsdatum,
        "email": a.email, "telefon": a.telefon,
        "plz": a.plz, "strasse": a.strasse, "ort": a.ort,
    }  # fmt: skip


def _treffer_dict(t) -> dict:
    h, p = t["haushalt"], t.get("person")
    return {
        "haushalt": {"kundennummer": h.kundennummer, "strasse": h.strasse, "plz": h.plz},
        "person": ({"vorname": p.vorname, "nachname": p.nachname, "geburtsdatum": p.geburtsdatum}
                   if p else None),
        "punkte": t["punkte"], "gruende": t["gruende"],
        "stufe": t["stufe"], "stufe_text": t["stufe_text"],
        "hinweise": [{"text": h2["text"], "art": h2["art"]} for h2 in t["hinweise"]],
        "folge": t["folge"],
    }  # fmt: skip


def _rechnen_dubletten():
    from apps.warteliste import ablauf

    return [
        {"a": _antrag_dict(p["a"]), "b": _antrag_dict(p["b"]),
         "gruende": p["gruende"], "punkte": p["punkte"]}
        for p in ablauf.dubletten()
    ]  # fmt: skip


def _rechnen_abgleich():
    from apps.warteliste import ablauf

    offene = ablauf.offene_antraege().select_related("wartestand").order_by("eingegangen_am")
    ergebnis = []
    for e in ablauf.kundenabgleich(offene):
        a = e["antrag"]
        try:
            status = a.wartestand.status
        except ObjectDoesNotExist:
            status = ""
        ergebnis.append(
            {"antrag_pk": a.pk, "antrag": _antrag_dict(a), "status": status,
             "sperr": e["sperr"], "treffer": [_treffer_dict(t) for t in e["treffer"]]}
        )  # fmt: skip
    return ergebnis


# ── Öffentlich ───────────────────────────────────────────────────────────────


def dubletten_daten():
    """(paare, frisch, laeuft) für die Dubletten-Seite."""
    return _holen(DUB, _sig_dubletten, _rechnen_dubletten)


def abgleich_daten():
    """(ergebnis_aller_offenen, frisch, laeuft) für die Abgleich-Seite."""
    return _holen(ABG, _sig_abgleich, _rechnen_abgleich)


def _anzahl(key) -> int | None:
    """Zahl der offenen Fälle aus dem Cache – ohne neu zu rechnen (fürs Menü-Abzeichen). ``None``,
    wenn noch nichts berechnet wurde; dann zeigt das Menü keine Zahl, statt teuer zu rechnen."""
    stand = cache.get(key)
    if stand and "daten" in stand:
        return len(stand["daten"])
    return None


def anzahl_abgleich() -> int | None:
    """Anträge mit noch nicht geprüftem Treffer im Kundenstamm (zuletzt berechneter Stand). Gezählt
    werden nur die, die auch die Abgleich-Seite in der Vorgabe zeigt (Status „neu“/„wartend“) –
    sonst stünde im Menü eine Zahl, aber die geöffnete Seite wäre leer (die übrigen stehen unter
    „alle offenen prüfen“)."""
    from apps.warteliste.models import Wartestand

    stand = cache.get(ABG)
    if not (stand and "daten" in stand):
        return None
    aktiv = {Wartestand.Status.NEU, Wartestand.Status.WARTEND}
    return sum(1 for e in stand["daten"] if e.get("status") in aktiv) or None


def anzahl_dubletten() -> int | None:
    """Mögliche Dubletten-Paare unter den offenen Anträgen (zuletzt berechneter Stand)."""
    return _anzahl(DUB)

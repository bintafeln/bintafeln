"""Regeln des Aufrufs (ADR 0050), übernommen aus dem bisherigen Aufrufsystem.

Die Reihenfolge eines Tages kommt direkt aus dem Kundenstamm: alle aktiven Haushalte der
Kundengruppen, die heute an der Ausgabestelle dran sind, in Gruppen nach Uhrzeit. Innerhalb einer
Gruppe kommen Haushalte mit Vorrang zuerst, beide Teile zufällig gemischt. Danach gleicht jeder
Schritt mit dem Kundenstamm ab: Neue Haushalte werden fair einsortiert, entfernte fallen heraus,
und wer heute schon eine Abholung hat (am Einlass eingelassen), verschwindet aus der Warteschlange.

Die ersten ``anzahl`` Nummern der laufenden Gruppe sind „aufgerufen“ (Bitte eintreten); „Weiter“
schiebt sie zu den Erledigten. Alle Änderungen laufen in einer Transaktion mit gesperrter Zeile.
"""

import datetime as dt
import random

from django.db import transaction
from django.urls import reverse
from django.utils import timezone

from apps.aufruf.models import AufrufEinstellungen, AufrufTag, KioskMeldung
from apps.aufruf.sprachen import sprachcode
from apps.ausgabe import ausgabetag
from apps.ausgabe.ampel import WOCHENTAGE, wochentage
from apps.kunden.models import Abholung, AusgabestelleZeit, Haushalt, Kundengruppe

AUFBEWAHREN_TAGE = 28
ABGLEICH_SEKUNDEN = 20  # so oft gleicht die Anzeige höchstens mit dem Kundenstamm ab
RUECKGAENGIG_MAX = 500  # ein ganzer Tag
TAGNAMEN = dict(AusgabestelleZeit.Wochentag.choices)


class AufrufFehler(Exception):
    pass


def norm(nummer) -> str:
    """Kundennummer vergleichbar machen: Leerzeichen weg, führende Nullen bei reinen Ziffern."""
    s = str(nummer).strip()
    return (s.lstrip("0") or "0") if s.isdigit() else s


def wochentag(stelle, datum: dt.date) -> int:
    """Wochentag des Datums; beim Probelauf der eingestellte (nur zum Ausprobieren)."""
    probe = AufrufEinstellungen.laden(stelle).wochentag_probe
    return datum.weekday() if probe is None else probe


def tagname(stelle, datum: dt.date) -> str:
    return TAGNAMEN[wochentag(stelle, datum)]


# ── Kundenstamm ──────────────────────────────────────────────────────────────


def gruppen_heute(stelle, datum: dt.date) -> list[Kundengruppe]:
    if AufrufEinstellungen.laden(stelle).wochentag_probe is None:
        return ausgabetag.gruppen_am(stelle, datum)  # mit Sonderausgaben (ADR 0072)
    kuerzel = WOCHENTAGE[wochentag(stelle, datum)]  # Probelauf: eingestellter Wochentag
    gruppen = [
        g for g in Kundengruppe.objects.filter(ausgabestelle=stelle, aktiv=True)
        if kuerzel in wochentage(g.wochentage)
    ]  # fmt: skip
    return sorted(gruppen, key=ausgabetag.reihenfolge)


def _hat_vorrang(haushalt, feld) -> bool:
    if feld.gilt_fuer == feld.GiltFuer.HAUSHALT:
        return haushalt.zusatz.get(feld.schluessel) is True
    return any(p.zusatz.get(feld.schluessel) is True for p in haushalt.personen.all())


def kandidaten(gruppe, einstellungen) -> tuple[list[str], set[str]]:
    """Kundennummern der aktiven Haushalte einer Gruppe und die mit Vorrang."""
    haushalte = Haushalt.objects.filter(kundengruppe=gruppe, status=Haushalt.Status.AKTIV)
    feld = einstellungen.vorrang_feld
    if feld is not None and feld.aktiv:
        haushalte = haushalte.prefetch_related("personen")
        vorrang = {h.kundennummer for h in haushalte if _hat_vorrang(h, feld)}
    else:
        vorrang = set()
    return [h.kundennummer for h in haushalte], vorrang


def _gemischt(nummern, vorrang) -> list[str]:
    zuerst = [n for n in nummern if n in vorrang]
    rest = [n for n in nummern if n not in vorrang]
    random.shuffle(zuerst)  # noqa: S311 – Reihenfolge, kein Geheimnis
    random.shuffle(rest)  # noqa: S311
    return zuerst + rest


def _zeit(gruppe) -> str:
    zeit = ausgabetag.beginn(gruppe)
    return zeit.strftime("%H:%M") if zeit else ""


def _gruppe_eintrag(gruppe, wartend) -> dict:
    return {"pk": gruppe.pk, "name": gruppe.name, "zeit": _zeit(gruppe),
            "wartend": wartend, "aufgerufen": [], "eingelassen": []}  # fmt: skip


def neuer_stand(stelle, datum, einstellungen) -> dict:
    gruppen, vorrang = [], set()
    for g in gruppen_heute(stelle, datum):
        nummern, v = kandidaten(g, einstellungen)
        vorrang |= v
        gruppen.append(_gruppe_eintrag(g, _gemischt(nummern, v)))
    stand = {"gruppen": gruppen, "index": 0, "rueckgaengig": [], "spaetzuender": {},
             "vorrang": sorted(vorrang)}  # fmt: skip
    _eingelassene_heraus(stand, datum, einstellungen, geschuetzt=False)
    _index_weiter(stand)
    return stand


def _eingelassen_heute(datum, nummern) -> set[str]:
    if not nummern:
        return set()
    return set(Abholung.objects.filter(datum=datum, haushalt__kundennummer__in=nummern)
               .values_list("haushalt__kundennummer", flat=True))  # fmt: skip


def _eingelassene_heraus(stand, datum, einstellungen, geschuetzt=True) -> None:
    """Wer heute schon abgeholt hat, aus der Warteschlange nehmen.

    ``geschuetzt``: die gerade angezeigten Nummern bleiben stehen (sonst sprängen sie weg).
    """
    if not einstellungen.eingelassene_ausblenden:
        return
    n = einstellungen.anzahl if geschuetzt else 0
    for i, g in enumerate(stand["gruppen"]):
        if i < stand["index"]:
            continue
        frei = g["wartend"][n:] if i == stand["index"] else g["wartend"]
        weg = _eingelassen_heute(datum, frei)
        if weg:
            fest = g["wartend"][:n] if i == stand["index"] else []
            g["wartend"] = fest + [x for x in frei if x not in weg]
            g["eingelassen"] += [x for x in frei if x in weg]
            # Platz merken, falls die Abholung zurückgenommen wird (Korrekturwunsch)
            nachfolger = stand.setdefault("nachfolger", {})
            for k, x in enumerate(frei):
                if x in weg:
                    nachfolger[x] = [y for y in frei[k + 1 :] if y not in weg][:50]


def _zurueckgenommene_hinein(stand, datum, einstellungen) -> None:
    """Eingelassene ohne Abholung (zurückgenommen) wieder an ihren alten Platz setzen.

    Alter Platz = vor dem ersten Nachfolger von damals, der noch wartet. Ist der Platz schon
    vorbei, kommt die Nummer als nächste dran (nie vor die gerade angezeigten Nummern).
    """
    n = einstellungen.anzahl
    nachfolger = stand.setdefault("nachfolger", {})
    for i, g in enumerate(stand["gruppen"]):
        if not g["eingelassen"]:
            continue
        noch = _eingelassen_heute(datum, g["eingelassen"])
        for x in [x for x in g["eingelassen"] if x not in noch]:
            g["eingelassen"].remove(x)
            folgende = nachfolger.pop(x, [])
            if stand["index"] >= len(stand["gruppen"]):  # Tag war schon fertig
                stand["index"] = len(stand["gruppen"]) - 1
            ziel = max(i, stand["index"])
            wartend = stand["gruppen"][ziel]["wartend"]
            fest = min(n, len(wartend)) if ziel == stand["index"] else 0
            if ziel == i:
                platz = next((k for k, y in enumerate(wartend) if k >= fest and y in folgende),
                             None)  # fmt: skip
                if platz is None:  # Nachfolger schon dran: als nächste; sonst war sie die letzte
                    vorbei = any(y not in wartend for y in folgende)
                    platz = fest if vorbei else len(wartend)
            else:
                platz = fest
            wartend.insert(platz, x)


def _index_weiter(stand) -> bool:
    """Leere Gruppen überspringen; True, wenn sich die laufende Gruppe geändert hat."""
    vorher = stand["index"]
    while (
        stand["index"] < len(stand["gruppen"]) and not stand["gruppen"][stand["index"]]["wartend"]
    ):
        stand["index"] += 1
    return stand["index"] != vorher


def abgleichen(stand, stelle, datum, einstellungen) -> None:
    """Mit dem Kundenstamm abgleichen (wie der Abgleich nach einem neuen Listen-Download früher).

    Laufende und kommende Gruppen: entfernte Haushalte fallen heraus (außer den gerade
    aufgerufenen), neue werden fair einsortiert – mit Vorrang hinter die wartenden mit Vorrang,
    die übrigen an zufällige Plätze, nie vor die gerade aufgerufenen Nummern.
    """
    n = einstellungen.anzahl
    vorrang = set(stand.get("vorrang", []))
    bekannt = {g["pk"] for g in stand["gruppen"]}
    heute_dran = gruppen_heute(stelle, datum)
    for gruppe in heute_dran:
        if gruppe.pk not in bekannt:  # heute neu dazugekommen
            stand["gruppen"].append(_gruppe_eintrag(gruppe, []))
    # Noch nicht begonnene Gruppen immer nach Beginn ordnen (z. B. Uhrzeit nachgetragen oder
    # Gruppe neu dazugekommen); laufende und erledigte bleiben, wo sie sind
    rang = {g.pk: k for k, g in enumerate(heute_dran)}
    start = stand["index"] + 1
    stand["gruppen"][start:] = sorted(stand["gruppen"][start:],
                                      key=lambda g: rang.get(g["pk"], len(rang)))  # fmt: skip
    pks = [g["pk"] for g in stand["gruppen"]]
    gruppen = {g.pk: g for g in Kundengruppe.objects.filter(pk__in=pks)}
    offen = [(i, g) for i, g in enumerate(stand["gruppen"]) if i >= stand["index"]]
    # 1. Entfernte Haushalte heraus (die gerade Aufgerufenen und spät Eingeordneten bleiben)
    frisch = {}
    for i, g in offen:
        gruppe = gruppen.get(g["pk"])
        nummern, v = kandidaten(gruppe, einstellungen) if gruppe else ([], set())
        frisch[i] = (nummern, v)
        vorrang |= v
        fest = g["wartend"][:n] if i == stand["index"] else []
        rest = [x for x in g["wartend"][len(fest):]
                if x in set(nummern) or x in stand["spaetzuender"]]  # fmt: skip
        g["wartend"] = fest + rest
        if gruppe:
            g["name"], g["zeit"] = gruppe.name, _zeit(gruppe)
    # 2. Neue Haushalte fair einsortieren
    im_stand = {x for g in stand["gruppen"] for teil in ("wartend", "aufgerufen", "eingelassen")
                for x in g[teil]}  # fmt: skip
    for i, g in offen:
        nummern, v = frisch[i]
        neu = [x for x in nummern if x not in im_stand]
        if not neu:
            continue
        neu_v = [x for x in neu if x in v]
        neu_r = [x for x in neu if x not in v]
        random.shuffle(neu_v)  # noqa: S311
        random.shuffle(neu_r)  # noqa: S311
        fest = g["wartend"][:n] if i == stand["index"] else []
        rest = g["wartend"][len(fest) :]
        vorn = 0
        while vorn < len(rest) and rest[vorn] in vorrang:
            vorn += 1
        regulaer = rest[vorn:]
        for x in neu_r:
            regulaer.insert(random.randint(0, len(regulaer)), x)  # noqa: S311
        g["wartend"] = fest + rest[:vorn] + neu_v + regulaer
        im_stand |= set(neu)
    stand["vorrang"] = sorted(vorrang)
    _zurueckgenommene_hinein(stand, datum, einstellungen)
    _eingelassene_heraus(stand, datum, einstellungen)
    _index_weiter(stand)
    stand["abgeglichen"] = timezone.now().isoformat()


# ── Tag laden und sperren ───────────────────────────────────────────────────


def _alte_loeschen(heute) -> None:
    AufrufTag.objects.filter(datum__lt=heute - dt.timedelta(days=AUFBEWAHREN_TAGE)).delete()
    KioskMeldung.objects.filter(datum__lt=heute).delete()


# ── Am Kiosk gemeldet ───────────────────────────────────────────────────────


def kiosk_melden(stelle, datum, nummer) -> None:
    """Ausweis am Kiosk gescannt: Der Kunde ist vermutlich da (grün in der Steuerung)."""
    KioskMeldung.objects.filter(datum__lt=datum).delete()  # nur der laufende Tag zählt
    h = _haushalt(norm(nummer))
    if h is not None:
        KioskMeldung.objects.get_or_create(ausgabestelle=stelle, datum=datum,
                                           kundennummer=h.kundennummer)  # fmt: skip


def am_kiosk(stelle, datum) -> set[str] | None:
    """Heute am Kiosk gemeldete Kundennummern; None, solange sich niemand gemeldet hat (dann
    färbt die Steuerung nichts, z. B. an Ausgabestellen ohne Kiosk)."""
    gemeldet = set(KioskMeldung.objects.filter(ausgabestelle=stelle, datum=datum)
                   .values_list("kundennummer", flat=True))  # fmt: skip
    return gemeldet or None


def tag_holen(stelle, datum, sperren=False) -> AufrufTag | None:
    abfrage = AufrufTag.objects.select_for_update() if sperren else AufrufTag.objects
    return abfrage.filter(ausgabestelle=stelle, datum=datum).first()


def _vorschau_sperren(stelle, datum, einstellungen) -> AufrufTag:
    """Tag (gesperrt) holen oder als Vorschau anlegen: Die Reihenfolge steht ab dann fest."""
    tag = tag_holen(stelle, datum, sperren=True)
    if tag is None:
        AufrufTag.objects.get_or_create(
            ausgabestelle=stelle, datum=datum,
            defaults={"stand": neuer_stand(stelle, datum, einstellungen)},
        )  # fmt: skip
        tag = tag_holen(stelle, datum, sperren=True)
    return tag


def vorschau(stelle, datum) -> AufrufTag | None:
    """Reihenfolge vor dem Start (Vorab-Abfrage am Kiosk); None, wenn heute keine Gruppe dran."""
    einstellungen = AufrufEinstellungen.laden(stelle)
    if tag_holen(stelle, datum) is None and not gruppen_heute(stelle, datum):
        return None
    with transaction.atomic():
        return _vorschau_sperren(stelle, datum, einstellungen)


def starten(stelle, datum) -> AufrufTag:
    """Tag starten; eine vorhandene Vorschau bleibt (die vorab genannten Plätze stimmen dann)."""
    einstellungen = AufrufEinstellungen.laden(stelle)
    with transaction.atomic():
        _alte_loeschen(datum)
        if tag_holen(stelle, datum) is None and not gruppen_heute(stelle, datum):
            raise AufrufFehler(f"Für {tagname(stelle, datum)} ist an dieser Ausgabestelle keine "
                               "Kundengruppe eingetragen.")  # fmt: skip
        tag = _vorschau_sperren(stelle, datum, einstellungen)
        if tag.gestartet_am is None:
            _eingelassene_heraus(tag.stand, datum, einstellungen, geschuetzt=False)
            abgleichen(tag.stand, stelle, datum, einstellungen)
            tag.gestartet_am = timezone.now()
            tag.save()
    return tag


def neu_mischen(stelle, datum) -> AufrufTag:
    """Neustart des Tages: alles neu gemischt, Fortschritt verworfen."""
    einstellungen = AufrufEinstellungen.laden(stelle)
    with transaction.atomic():
        tag = _vorschau_sperren(stelle, datum, einstellungen)
        tag.stand = neuer_stand(stelle, datum, einstellungen)
        tag.gestartet_am = timezone.now()
        tag.save()
    return tag


def _gestartet_sperren(stelle, datum) -> AufrufTag:
    tag = tag_holen(stelle, datum, sperren=True)
    if tag is None or tag.gestartet_am is None:
        raise AufrufFehler(
            f"Die Ausgabe für diesen {tagname(stelle, datum)} ist noch nicht gestartet."
        )
    return tag


def weiter(stelle, datum) -> AufrufTag:
    """Die aufgerufenen Nummern sind erledigt; die nächsten werden aufgerufen."""
    einstellungen = AufrufEinstellungen.laden(stelle)
    with transaction.atomic():
        tag = _gestartet_sperren(stelle, datum)
        if tag.stand["index"] < len(tag.stand["gruppen"]):
            _weiter_im_stand(tag.stand, stelle, datum, einstellungen)
            tag.save()
    return tag


def _weiter_im_stand(s, stelle, datum, einstellungen) -> None:
    g = s["gruppen"][s["index"]]
    weg = g["wartend"][: einstellungen.anzahl]
    g["wartend"] = g["wartend"][len(weg) :]
    g["aufgerufen"] += weg
    index_vorher = s["index"]
    _eingelassene_heraus(s, datum, einstellungen, geschuetzt=False)  # vor dem Anzeigen
    _index_weiter(s)
    s["rueckgaengig"] = [*s["rueckgaengig"], {
        "gruppe": index_vorher, "nummern": weg, "zeit": timezone.localtime().strftime("%H:%M"),
        "zeitpunkt": timezone.now().isoformat(),
    }][-RUECKGAENGIG_MAX:]  # fmt: skip
    abgleichen(s, stelle, datum, einstellungen)


def zurueck(stelle, datum) -> AufrufTag:
    """Letztes „Weiter“ rückgängig machen."""
    with transaction.atomic():
        tag = _gestartet_sperren(stelle, datum)
        s = tag.stand
        if not s["rueckgaengig"]:
            raise AufrufFehler("Keine Aktion zum Rückgängigmachen verfügbar.")
        schritt = s["rueckgaengig"].pop()
        s["index"] = schritt["gruppe"]
        g = s["gruppen"][schritt["gruppe"]]
        # Inzwischen spät Eingeordnete stehen schon weiter hinten und bleiben dort
        zurueck_ = [x for x in schritt["nummern"] if x not in s["spaetzuender"]]
        for x in zurueck_:
            if x in g["aufgerufen"]:
                g["aufgerufen"].remove(x)
        g["wartend"] = zurueck_ + [x for x in g["wartend"] if x not in zurueck_]
        tag.save()
    return tag


# ── Abfrage und Spätzünder ──────────────────────────────────────────────────


def _finden(s, nummer):
    """(Gruppenindex, Position in aufgerufen+wartend, Anzahl aufgerufen) oder None."""
    for i, g in enumerate(s["gruppen"]):
        voll = g["aufgerufen"] + g["wartend"]
        for j, x in enumerate(voll):
            if norm(x) == nummer:
                return i, j, len(g["aufgerufen"])
    return None


def _davor(s, i, j, aufgerufen) -> int:
    """Wartende vor dieser Stelle, ab der laufenden Gruppe."""
    vor = j - aufgerufen
    for k in range(s["index"], i):
        vor += len(s["gruppen"][k]["wartend"])
    return vor


def _gesamtplatz(s, i, j) -> int:
    return sum(len(g["aufgerufen"]) + len(g["wartend"]) for g in s["gruppen"][:i]) + j + 1


def spaetzuender(stelle, datum, nummer) -> dict:
    """Schon Aufgerufenen ``spaetzuender_versatz`` wartende Plätze nach hinten setzen."""
    einstellungen = AufrufEinstellungen.laden(stelle)
    nummer = norm(nummer)
    with transaction.atomic():
        tag = _gestartet_sperren(stelle, datum)
        s = tag.stand
        abholung = _abholung_heute(nummer, datum)
        if abholung:
            um = f" um {abholung.uhrzeit:%H:%M}" if abholung.uhrzeit else ""
            raise AufrufFehler(f"Kunde {nummer} hat heute{um} schon abgeholt und war am Einlass. "
                               "Nicht neu einsortieren.")  # fmt: skip
        if nummer in {norm(x) for x in s["spaetzuender"]}:
            ergebnis = _abfrage_ergebnis(tag, nummer)
            return {"bereits": True, "neuer_platz": ergebnis.get("gesamt_platz", 0),
                    "vor_der_nummer": ergebnis.get("vor_der_nummer", 0),
                    "versatz": einstellungen.spaetzuender_versatz}  # fmt: skip
        gefunden = None
        for g in s["gruppen"]:
            for x in g["aufgerufen"]:
                if norm(x) == nummer:
                    gefunden = (g, x)
                    break
            if gefunden:
                break
        if gefunden is None:
            raise AufrufFehler(f"Kunde {nummer} wurde heute noch nicht aufgerufen oder ist nicht "
                               "in der Liste.")  # fmt: skip
        g, x = gefunden
        g["aufgerufen"].remove(x)
        wartende = [(k, pos) for k in range(s["index"], len(s["gruppen"]))
                    for pos in range(len(s["gruppen"][k]["wartend"]))]  # fmt: skip
        versatz = max(einstellungen.spaetzuender_versatz, einstellungen.anzahl)
        if len(wartende) > versatz:
            k, pos = wartende[versatz]
            s["gruppen"][k]["wartend"].insert(pos, x)
        elif wartende:
            k = wartende[-1][0]
            s["gruppen"][k]["wartend"].append(x)
        else:
            k = min(s["index"], len(s["gruppen"]) - 1)
            s["gruppen"][k]["wartend"].append(x)
            s["index"] = k
        i, j, aufg = _finden(s, nummer)
        s["spaetzuender"][x] = {
            "zeitpunkt": timezone.now().isoformat(),
            "neuer_platz": _gesamtplatz(s, i, j), "ziel_gruppe": s["gruppen"][k]["name"],
            "versatz": einstellungen.spaetzuender_versatz,
            "zeit": timezone.localtime().strftime("%H:%M"),
        }  # fmt: skip
        tag.save()
        return {"bereits": False, "neuer_platz": _gesamtplatz(s, i, j),
                "vor_der_nummer": _davor(s, i, j, aufg),
                "versatz": einstellungen.spaetzuender_versatz}  # fmt: skip


def _haushalt(nummer) -> Haushalt | None:
    h = Haushalt.objects.filter(kundennummer=nummer).first()
    if h is None and nummer.isdigit():
        h = next((x for x in Haushalt.objects.filter(kundennummer__endswith=nummer)
                  if norm(x.kundennummer) == nummer), None)  # fmt: skip
    return h


def _sprache(nummer) -> str | None:
    h = _haushalt(nummer)
    p = h.hauptperson if h else None
    return sprachcode(p.staatsangehoerigkeit) if p else None


def _abholung_heute(nummer, datum) -> Abholung | None:
    """Heutige Abholung zur Kundennummer: Der Kunde ist dann schon am Einlass gewesen."""
    h = _haushalt(nummer)
    if h is None:
        return None
    return Abholung.objects.filter(haushalt=h, datum=datum).order_by("uhrzeit").first()


def _abgeholt(ergebnis, abholung) -> dict:
    uhrzeit = abholung.uhrzeit.strftime("%H:%M") if abholung.uhrzeit else ""
    return {**ergebnis, "schon_dran": True, "abgeholt": True, "abgeholt_um": uhrzeit,
            "neu_einsortiert": False}  # fmt: skip


def _abfrage_ergebnis(tag, nummer) -> dict:
    s = tag.stand
    tag_name = tagname(tag.ausgabestelle, tag.datum)
    aktuell = s["gruppen"][s["index"]]["name"] if s["index"] < len(s["gruppen"]) else None
    gesamt = sum(len(g["aufgerufen"]) + len(g["wartend"]) for g in s["gruppen"])
    basis = {"active": True, "nummer": nummer, "tag": tag_name,
             "vorschau": tag.gestartet_am is None, "sprache": _sprache(nummer)}  # fmt: skip
    treffer = _finden(s, nummer)
    abholung = _abholung_heute(nummer, tag.datum)
    if treffer is None:
        if any(norm(x) == nummer for g in s["gruppen"] for x in g["eingelassen"]):
            ergebnis = {**basis, "gefunden": True, "schon_dran": True, "eingelassen": True,
                        "gruppe": "", "gruppen_platz": 0, "gruppen_gesamt": 0, "gesamt_platz": 0,
                        "gesamt_anzahl": gesamt, "vor_der_nummer": 0,
                        "aktuelle_gruppe": aktuell}  # fmt: skip
            return _abgeholt(ergebnis, abholung) if abholung else ergebnis
        return {
            **basis,
            "gefunden": False,
            "message": f"Kundennummer {nummer} ist heute ({tag_name}) nicht in der Liste.",
        }
    i, j, aufg = treffer
    g = s["gruppen"][i]
    schon_dran = j < aufg
    # Steht die Nummer gerade auf dem Monitor („Bitte eintreten“), ist sie jetzt dran – nicht
    # „gleich“. Erst wer danach kommt, wartet noch.
    anzahl = AufrufEinstellungen.laden(tag.ausgabestelle).anzahl if tag.gestartet_am else 0
    jetzt = bool(anzahl) and i == s["index"] and aufg <= j < aufg + anzahl
    vor = 0 if schon_dran or jetzt else _davor(s, i, j, aufg)
    auf_monitor = min(anzahl, len(s["gruppen"][s["index"]]["wartend"])) if aktuell else 0
    ergebnis = {**basis, "gefunden": True, "schon_dran": schon_dran, "jetzt_dran": jetzt,
                "gruppe": g["name"], "gruppen_platz": j + 1,
                "gruppen_gesamt": aufg + len(g["wartend"]),
                "gesamt_platz": _gesamtplatz(s, i, j), "gesamt_anzahl": gesamt,
                "vor_der_nummer": vor,
                # so viele Nummern kommen noch auf den Monitor, bevor diese dort erscheint
                "vor_aufruf": max(vor - auf_monitor, 0),
                "aktuelle_gruppe": aktuell}  # fmt: skip
    if any(norm(x) == nummer for x in s["spaetzuender"]):
        ergebnis.update(schon_dran=True, neu_einsortiert=True, jetzt_dran=False)
    if abholung:
        return _abgeholt(ergebnis, abholung)
    return ergebnis


def abfrage(stelle, datum, nummer) -> dict:
    """Wo steht eine Kundennummer heute? Vor dem Start gegen die Vorschau (Vorab-Abfrage)."""
    nummer = norm(nummer)
    tag = tag_holen(stelle, datum) or vorschau(stelle, datum)
    if tag is None:
        return {"active": False, "message": "Zurzeit läuft keine Ausgabe.",
                "sprache": _sprache(nummer)}  # fmt: skip
    return _abfrage_ergebnis(tag, nummer)


# ── Anzeige ─────────────────────────────────────────────────────────────────


def aktualisieren(stelle, datum) -> AufrufTag | None:
    """Gestarteten Tag laden; höchstens alle ABGLEICH_SEKUNDEN mit dem Kundenstamm abgleichen."""
    tag = tag_holen(stelle, datum)
    if tag is None or tag.gestartet_am is None:
        return tag
    einstellungen = AufrufEinstellungen.laden(stelle)
    zuletzt = tag.stand.get("abgeglichen")
    if zuletzt and timezone.now() - dt.datetime.fromisoformat(zuletzt) < dt.timedelta(
        seconds=ABGLEICH_SEKUNDEN
    ):
        return tag
    with transaction.atomic():
        tag = tag_holen(stelle, datum, sperren=True)
        abgleichen(tag.stand, stelle, datum, einstellungen)
        tag.save()
    return tag


def stand_fuer_anzeige(tag, einstellungen, datum, eingelassene_zeigen=False) -> dict:
    """Antwort für Monitor, Anzeige und Mobil (Felder wie im bisherigen Aufrufsystem).

    ``eingelassene_zeigen``: Der große Monitor draußen zeigt die aufgerufenen Nummern bis zum
    nächsten „Weiter“, auch wenn sie schon am Einlass sind; alle anderen Anzeigen nehmen sie
    sofort heraus. Weiter geht es nur mit dem Knopf, nie von selbst."""
    if tag is None or tag.gestartet_am is None:
        return {
            "error": f"Die Ausgabe für diesen {tagname(einstellungen.ausgabestelle, datum)} "
            "ist noch nicht aktiviert"
        }
    s = tag.stand
    tag_name = tagname(tag.ausgabestelle, tag.datum)
    # „Erledigt“ zählt die heute schon Eingelassenen (mit Abholung), nicht die aufgerufenen Batches:
    # So wächst der Zähler, sobald jemand hereinkommt, nicht erst beim nächsten „Weiter“. „Gesamt“
    # ist die ganze heutige Menge (auch schon Eingelassene), damit der Nenner stabil bleibt.
    alle_nummern = [x for g in s["gruppen"]
                    for teil in ("wartend", "aufgerufen", "eingelassen")
                    for x in g[teil]]  # fmt: skip
    gesamt = len(alle_nummern)
    erledigt = len(_eingelassen_heute(datum, alle_nummern))
    kann_zurueck = bool(s["rueckgaengig"])
    if s["index"] >= len(s["gruppen"]):
        return {"finished": True, "selected_day": tag_name, "can_undo": kann_zurueck,
                "total_completed": erledigt, "total_numbers": gesamt}  # fmt: skip
    n = einstellungen.anzahl
    g = s["gruppen"][s["index"]]
    wartend = g["wartend"]
    vorrang = set(s.get("vorrang", [])) if einstellungen.vorrang_symbol else set()
    # Wer gerade aufgerufen ist und schon am Einlass war, verschwindet sofort aus „Bitte
    # eintreten“; der Platz bleibt bis zum nächsten „Weiter“ leer (keiner wird nachgerufen).
    aufgerufen, danach = wartend[:n], wartend[n : n + 60]
    if einstellungen.eingelassene_ausblenden:
        # Auch aus „Danach“ sofort heraus (aus der Warteschlange erst beim nächsten Abgleich)
        schon_da = _eingelassen_heute(datum, aufgerufen + danach)
        if not eingelassene_zeigen:
            aufgerufen = [x for x in aufgerufen if x not in schon_da]
        danach = [x for x in danach if x not in schon_da]
    # Geht die laufende Gruppe zu Ende, kommt danach die nächste: ihre ersten Nummern zeigen,
    # damit „Danach“ nicht leer ist, obwohl noch Kunden warten (sie werden erst aufgerufen,
    # wenn die laufende Gruppe durch ist).
    folgende, folgende_titel = [], ""
    if len(danach) < 10:
        naechste = next((g2 for g2 in s["gruppen"][s["index"] + 1 :] if g2["wartend"]), None)
        if naechste:
            folgende = naechste["wartend"][:30]
            if einstellungen.eingelassene_ausblenden:
                schon = _eingelassen_heute(datum, folgende)
                folgende = [x for x in folgende if x not in schon]
            folgende, folgende_titel = folgende[: 10 - len(danach)], gruppe_titel(naechste)
    vergangen = []
    for schritt in reversed(s["rueckgaengig"]):
        vergangen += schritt["nummern"]
        if len(vergangen) >= 10:
            break
    # Am Kiosk gemeldet: grün, sonst dunkelrot; ohne Meldung heute keine Farben (None)
    kiosk = am_kiosk(tag.ausgabestelle, datum)

    def da(nummern):
        return None if kiosk is None else [x in kiosk for x in nummern]

    return {
        "finished": False,
        "current_numbers": aufgerufen,
        # Alle Aufgerufenen schon am Einlass: Die Gruppe läuft weiter, nur „Weiter“ drücken
        "alle_eingelassen": bool(wartend[:n]) and not aufgerufen and not eingelassene_zeigen,
        "next_numbers": danach[:10],
        "upcoming_numbers": danach,
        "past_numbers": vergangen[:10],
        "current_slot": gruppe_titel(g),
        "selected_day": tag_name,
        "priority_flags": [x in vorrang for x in aufgerufen],
        "next_priority_flags": [x in vorrang for x in danach],
        "present_flags": da(aufgerufen),
        "next_present_flags": da(danach),
        "following_numbers": folgende,
        "following_slot": folgende_titel if folgende else "",
        "following_priority_flags": [x in vorrang for x in folgende],
        "following_present_flags": da(folgende),
        "past_present_flags": da(vergangen[:10]),
        "kiosk_numbers": None if kiosk is None else sorted(kiosk),
        "remaining_count": len(wartend),
        "slot_index": s["index"] + 1,
        "total_slots": len(s["gruppen"]),
        "slot_completed": len(g["aufgerufen"]),
        "slot_total": len(g["aufgerufen"]) + len(wartend),
        "total_completed": erledigt,
        "total_numbers": gesamt,
        "can_undo": kann_zurueck,
    }


def gruppe_titel(g) -> str:
    """Name mit Uhrzeit, außer die Zeit steht schon im Namen („Zentrale Mo 13:00-14:00“)."""
    zeit = g.get("zeit", "")
    if not zeit or zeit in g["name"] or zeit.replace(":", ".") in g["name"]:
        return g["name"]
    return f"{g['name']} ({zeit})"


def reihenfolge(tag) -> list[dict]:
    """Ganze Reihenfolge des Tages (für die Liste): erledigt, wartend, eingelassen."""
    zeilen, platz = [], 0
    s = tag.stand
    for g in s["gruppen"]:
        for j, x in enumerate(g["aufgerufen"] + g["wartend"], start=1):
            platz += 1
            info = s["spaetzuender"].get(x)
            anmerkung = (f"zu spät – auf Platz {info['neuer_platz']} gesetzt ({info['zeit']} Uhr)"
                         if info else "")  # fmt: skip
            zeilen.append({"platz": platz, "gruppe": gruppe_titel(g), "gruppen_platz": j,
                           "nummer": x, "aufgerufen": j <= len(g["aufgerufen"]),
                           "anmerkung": anmerkung})  # fmt: skip
        for x in g["eingelassen"]:
            zeilen.append({"platz": "", "gruppe": gruppe_titel(g), "gruppen_platz": "",
                           "nummer": x, "aufgerufen": False,
                           "anmerkung": "vorher eingelassen"})  # fmt: skip
    return zeilen


# ── Einlass ─────────────────────────────────────────────────────────────────


def _aufgerufen_um(s, x):
    """Zeitpunkt (aware) des letzten Aufrufs dieser Nummer, sonst None."""
    for schritt in reversed(s["rueckgaengig"]):
        if x in schritt["nummern"]:
            if schritt.get("zeitpunkt"):
                return dt.datetime.fromisoformat(schritt["zeitpunkt"])
            stunde, minute = (int(t) for t in schritt["zeit"].split(":"))
            return timezone.localtime().replace(hour=stunde, minute=minute, second=0)
    return None


# Für die Ampel am Einlass: grün bleibt, gelb blinkt dazu (ampel.modul_hinweise_beachten)
ZU_FRUEH = {"ampel": "Kunde ist zu früh (Aufruf)", "wort": "ZU FRÜH"}
ZU_SPAET = {"ampel": "Kunde ist zu spät (Aufruf)", "wort": "ZU SPÄT"}


def _verschieben_knopf(tag, e, haushalt) -> dict:
    """Knopf am Einlass: zu spät Gekommene neu einsortieren (wie „zu spät gekommen“ am Handy)."""
    versatz = max(e.spaetzuender_versatz, e.anzahl)  # wie spaetzuender()
    return {
        "recht": "aufruf.steuern",
        "url": reverse("aufruf:verschieben", args=[tag.ausgabestelle_id, haushalt.kundennummer]),
        "text": f"{versatz} Nummern verschieben",
        "erklaerung": (
            f"Kunde {haushalt.kundennummer} kommt zurück in die Warteschlange: {versatz} wartende "
            "Nummern hinter den gerade aufgerufenen. Monitor und Ampel zeigen ihn dann als „noch "
            "nicht dran“, bis er wieder aufgerufen wird. Das geht einmal am Tag. Die Zahl steht "
            "unter Einstellungen → Aufruf, Monitor und Kiosk („Zu spät Gekommene: Plätze nach "
            "hinten“)."
        ),
    }


def _handys(haushalt) -> list[dict]:
    """Eingerichtete Handys für „Wartezeit aufs Handy“ mit Knopf zum Zurücksetzen (ADR 0090)."""
    from apps.aufruf.models import HandyZugang

    anzahl = HandyZugang.objects.filter(kundennummer=haushalt.kundennummer).count()
    if not anzahl:
        return []
    return [{"text": f"Wartezeit aufs Handy: {anzahl} Handy{'s' if anzahl != 1 else ''} "
             "eingerichtet", "farbe": "info", "knopf": {
                 "recht": "aufruf.steuern", "text": "Handys zurücksetzen",
                 "url": reverse("aufruf:handys_zuruecksetzen", args=[haushalt.kundennummer]),
                 "erklaerung": "Meldet alle Handys dieses Haushalts ab, z. B. bei neuem oder "
                 "verlorenem Handy. Der Kunde meldet sich danach neu mit Kundennummer und "
                 "Geburtsdatum an."}}]  # fmt: skip


def einlass(haushalt, heute, stelle=None) -> list[dict]:
    """Hinweise für die Einlass-Karte: Handys für die Wartezeit und wann aufgerufen, zu spät oder
    noch nicht dran. An einer Ausgabestelle ohne Aufruf erscheint nichts."""
    if stelle is not None and not AufrufEinstellungen.laden(stelle).aktiv:
        return []
    return _handys(haushalt) + _einlass_aufruf(haushalt, heute, stelle)


def _einlass_aufruf(haushalt, heute, stelle=None) -> list[dict]:
    gruppe = haushalt.kundengruppe
    stellen = [s for s in (gruppe.ausgabestelle if gruppe else None, stelle) if s]
    tag = next((t for t in (tag_holen(s, heute) for s in stellen) if t), None)
    if tag is None or tag.gestartet_am is None:
        return []
    e = AufrufEinstellungen.laden(tag.ausgabestelle)
    if not e.aktiv:
        return []
    s = tag.stand
    nummer = norm(haushalt.kundennummer)
    treffer = _finden(s, nummer)
    if treffer is None:
        if any(norm(x) == nummer for g in s["gruppen"] for x in g["eingelassen"]):
            return []
        return [{"text": "Nicht in der heutigen Aufruf-Liste", "farbe": "info"}]
    i, j, aufg = treffer
    g = s["gruppen"][i]
    x = (g["aufgerufen"] + g["wartend"])[j]
    if x in s["spaetzuender"]:
        info = s["spaetzuender"][x]
        if j >= aufg:
            vor = _davor(s, i, j, aufg)
            if vor < e.anzahl and i == s["index"]:
                return [{"text": f"Kam zu spät, um {info['zeit']} Uhr neu einsortiert – jetzt an "
                         "der Reihe", "farbe": "gelb"}]  # fmt: skip
            return [{"text": f"Kam zu spät, um {info['zeit']} Uhr neu einsortiert – noch {vor} "
                     "Nummern zu früh", "farbe": "gelb", **ZU_FRUEH}]  # fmt: skip
    if j < aufg:
        um = _aufgerufen_um(s, x)
        if um is None:
            return [{"text": "Schon aufgerufen", "farbe": "gruen"}]
        minuten = int((timezone.now() - um).total_seconds() // 60)
        uhr = timezone.localtime(um).strftime("%H:%M")
        if e.zu_spaet_minuten and minuten > e.zu_spaet_minuten:
            return [{"text": f"Zu spät: aufgerufen um {uhr} Uhr (vor {minuten} Minuten)",
                     "farbe": "rot", "knopf": _verschieben_knopf(tag, e, haushalt),
                     **ZU_SPAET}]  # fmt: skip
        return [{"text": f"Aufgerufen um {uhr} Uhr (vor {minuten} Minuten)", "farbe": "gruen"}]
    if i == s["index"] and j - aufg < e.anzahl:
        return [{"text": "Gerade aufgerufen – „Bitte eintreten“", "farbe": "gruen"}]
    vor = _davor(s, i, j, aufg)
    return [{"text": f"Noch nicht aufgerufen: {vor} Nummer{'n' if vor != 1 else ''} zu früh",
             "farbe": "gelb", **ZU_FRUEH}]  # fmt: skip

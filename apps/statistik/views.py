"""Seite Statistik (ADR 0036): Kennzahlen und Diagramme, je Abschnitt als Tabelle und CSV."""

import csv
import datetime as dt

from django.http import HttpResponse
from django.shortcuts import render
from django.utils import timezone

from apps.core.pdf import pdf_antwort
from apps.konten import rollen
from apps.kunden import zugang
from apps.kunden.models import Ausgabestelle
from apps.statistik import auswertung as aw
from apps.statistik import diagramme as dg
from apps.statistik import jahresbericht as jb


def _datum(text) -> dt.date | None:
    try:
        return dt.date.fromisoformat(text)
    except (TypeError, ValueError):
        return None


def _zeitraum(request, heute):
    vorgaben = aw.zeitraeume(heute)
    wahl = request.GET.get("zeitraum", "12monate")
    if wahl == "eigen":
        von, bis = _datum(request.GET.get("von")), _datum(request.GET.get("bis"))
        if von and bis and von <= bis:
            return wahl, aw.Zeitraum(von, bis, f"{von:%d.%m.%Y} – {bis:%d.%m.%Y}"), vorgaben
        wahl = "12monate"
    if wahl not in vorgaben:
        wahl = "12monate"
    return wahl, vorgaben[wahl], vorgaben


def _stellen(request):
    """Gewählte Ausgabestellen; Mitarbeitende einer Ausgabestelle nur die eigenen."""
    erlaubt = zugang.stellen(request.user)
    auswahl = list(erlaubt) if erlaubt is not None else list(Ausgabestelle.objects.order_by("name"))
    gewaehlt = request.GET.get("stelle", "")
    treffer = [s for s in auswahl if str(s.pk) == gewaehlt]
    if treffer:
        return treffer, auswahl, gewaehlt
    return (erlaubt if erlaubt is not None else None), auswahl, ""


def _euro(wert) -> str:
    return f"{wert:,.2f} €".replace(",", "X").replace(".", ",").replace("X", ".")


def _verein(benutzer, stellen) -> tuple[bool, bool]:
    """Spenden bzw. Mitglieder zeigen? Nur ohne Ausgabestelle und mit dem Recht des Bereichs."""
    if stellen is not None or benutzer is None:
        return False, False
    return (rollen.hat_recht(benutzer, "spenden.sehen"),
            rollen.hat_recht(benutzer, "mitglieder.sehen"))  # fmt: skip


def _versteckt(get, kennung) -> set[int]:
    """Welche Reihen des Abschnitts hat die Legende ausgeblendet (?aus_<id>=0,2)?"""
    if get is None:
        return set()
    roh = get.get(f"aus_{kennung}", "")
    return {int(t) for t in roh.split(",") if t.strip().isdigit()}


def _umschalten(get, kennung, aus: set[int], index: int) -> str:
    """Abfrage, die genau diese eine Reihe aus- bzw. wieder einblendet (für den Legenden-Link)."""
    if get is None:  # PDF-Jahresbericht: keine anklickbare Legende
        return ""
    neu_aus = (aus - {index}) if index in aus else (aus | {index})
    p = get.copy()
    schluessel = f"aus_{kennung}"
    if neu_aus:
        p[schluessel] = ",".join(str(i) for i in sorted(neu_aus))
    elif schluessel in p:
        del p[schluessel]
    p.pop("csv", None)
    return p.urlencode()


def _einheit(z: aw.Zeitraum) -> str:
    return {"tag": "Tag", "woche": "Woche", "monat": "Monat"}[z.einheit]


def _linien_quelle(kennung, z, stellen, benutzer):
    """Die Reihen, Überschrift, Diagrammtitel und Erläuterung eines Verlaufs-Abschnitts – oder
    ``None``, wenn es ihn bei dieser Auswahl nicht gibt. Beide Wege (ganze Seite und das Nachladen
    eines einzelnen Abschnitts) nutzen dieselbe Quelle, damit Texte nicht auseinanderlaufen."""
    einheit = _einheit(z)
    if kennung == "verlauf_stellen":
        serien = aw.verlauf_je_stelle(z, stellen)
        if len(serien) <= 1:
            return None
        return (
            serien,
            f"Abholungen je Ausgabestelle und {einheit}",
            "Abholungen je Ausgabestelle",
            "Jede Ausgabestelle behält ihre Farbe; mehr als acht werden zu „Andere“. "
            "Ein Tippen auf die Legende blendet eine Ausgabestelle aus; die Achse passt sich an.",
        )
    if kennung == "neuaufnahmen":
        return (
            aw.neuaufnahmen_und_antraege(z, stellen),
            f"Neue Kunden und Anträge je {einheit}",
            "Neue Kunden und Anträge",
            "Neue Kunden nach „Kunde seit“. Anträge nur ohne Auswahl einer Ausgabestelle.",
        )
    if kennung == "mitglieder":
        if not _verein(benutzer, stellen)[1]:
            return None
        return (
            aw.mitglieder_ein_und_austritte(z),
            f"Eintritte und Austritte je {einheit}",
            "Eintritte und Austritte",
            "",
        )
    return None


def _linien_dict(kennung, serien, titel, diagramm_titel, beschriftung, einheit, get, text=""):
    """Verlaufs-Abschnitt mit anklickbarer Legende: ausgeblendete Reihen fallen aus der Zeichnung,
    dadurch skaliert die Y-Achse neu. Tabelle und CSV bleiben vollständig."""
    aus = _versteckt(get, kennung)
    sichtbar = [s for i, s in enumerate(serien) if i not in aus]
    return {
        "id": kennung,
        "titel": titel,
        "svg": dg.linien(beschriftung, sichtbar, diagramm_titel),
        "kopf": [einheit, *[s.name for s in serien]],
        "zeilen": [[b, *[int(s.werte[i]) for s in serien]] for i, b in enumerate(beschriftung)],
        "text": text,
        "legende": [
            {
                "name": s.name,
                "farbe": s.farbe,
                "aus": i in aus,
                "abfrage": _umschalten(get, kennung, aus, i),
            }
            for i, s in enumerate(serien)
        ],
    }


def linien_abschnitt(kennung, z, stellen, benutzer, get):
    """Nur einen Verlaufs-Abschnitt bauen (für das schnelle Nachladen beim Legenden-Klick, ohne
    die ganze Seite neu zu berechnen). ``None``, wenn es den Abschnitt nicht gibt."""
    quelle = _linien_quelle(kennung, z, stellen, benutzer)
    if quelle is None:
        return None
    serien, titel, diagramm_titel, text = quelle
    beschriftung = [name for _, name in aw.perioden(z)]
    return _linien_dict(
        kennung, serien, titel, diagramm_titel, beschriftung, _einheit(z), get, text
    )


def abschnitte(z: aw.Zeitraum, stellen, heute, benutzer=None, get=None) -> list[dict]:
    """Alle Abschnitte mit Diagramm, Tabelle und Erklärung. ``get`` (die Abfrageparameter der
    Seite) steuert die anklickbare Legende; ohne ``get`` (PDF-Jahresbericht) sind alle Reihen zu
    sehen."""
    beschriftung = [name for _, name in aw.perioden(z)]
    einheit = _einheit(z)
    liste = []

    def neu(kennung, titel, svg, kopf, zeilen, text="", legende=()):
        liste.append(
            {
                "id": kennung,
                "titel": titel,
                "svg": svg,
                "kopf": kopf,
                "zeilen": zeilen,
                "text": text,
                "legende": [(r.name, r.farbe) for r in legende],
            }
        )

    def linien_neu(kennung):
        quelle = _linien_quelle(kennung, z, stellen, benutzer)
        if quelle is not None:
            serien, titel, diagramm_titel, text = quelle
            liste.append(
                _linien_dict(
                    kennung, serien, titel, diagramm_titel, beschriftung, einheit, get, text
                )
            )

    werte = aw.verlauf(aw.abholungen(z, stellen), z)
    daten = list(zip(beschriftung, werte, strict=True))
    neu(
        "abholungen",
        f"Abholungen je {einheit}",
        dg.saeulen(daten, "Abholungen"),
        [einheit, "Abholungen"],
        [[n, int(w)] for n, w in daten],
    )

    linien_neu("verlauf_stellen")
    je_stelle = aw.je_stelle(z, stellen)
    neu(
        "stellen",
        "Abholungen je Ausgabestelle",
        dg.balken(je_stelle, "Abholungen je Ausgabestelle"),
        ["Ausgabestelle", "Abholungen"],
        [[n, w] for n, w in je_stelle],
    )

    wochentage = aw.je_wochentag(z, stellen)
    neu(
        "wochentage",
        "Abholungen nach Wochentag",
        dg.saeulen(wochentage, "Wochentage"),
        ["Wochentag", "Abholungen"],
        [[n, w] for n, w in wochentage],
    )
    stunden = aw.je_stunde(z, stellen)
    if stunden:
        neu(
            "uhrzeit",
            "Abholungen nach Uhrzeit",
            dg.saeulen(stunden, "Uhrzeit", farbe=0),
            ["Stunde", "Abholungen"],
            [[n, w] for n, w in stunden],
            "Nur Abholungen mit Uhrzeit (am Einlass gebucht).",
        )

    einnahmen = aw.verlauf(aw.einnahmen(z, stellen), z, wert="bar")
    daten = list(zip(beschriftung, einnahmen, strict=True))
    neu(
        "einnahmen",
        f"Bareinnahmen je {einheit}",
        dg.saeulen(daten, "Bareinnahmen", " €", nachkomma=2),
        [einheit, "Euro"],
        [[n, f"{w:.2f}".replace(".", ",")] for n, w in daten],
        "Bar eingenommenes Geld laut Kundenkonto (Beiträge und Einzahlungen).",
    )

    linien_neu("neuaufnahmen")

    groessen = aw.haushaltsgroessen(heute, stellen)
    neu(
        "haushaltsgroessen",
        "Aktive Haushalte nach Größe (Personen)",
        dg.saeulen(groessen, "Haushaltsgrößen", farbe=2),
        ["Personen", "Haushalte"],
        [[n, w] for n, w in groessen],
        "Heutiger Stand, unabhängig vom Zeitraum.",
    )
    alter = aw.altersgruppen(heute, stellen)
    neu(
        "alter",
        "Personen in aktiven Haushalten nach Alter",
        dg.saeulen(alter, "Altersgruppen", farbe=2),
        ["Alter", "Personen"],
        [[n, w] for n, w in alter],
        "Heutiger Stand.",
    )
    status = aw.status(stellen)
    neu(
        "status",
        "Haushalte nach Status",
        dg.balken(status, "Status", farbe=0),
        ["Status", "Haushalte"],
        [[n, w] for n, w in status],
        "Heutiger Stand.",
    )
    arten = aw.einkommensarten(stellen)
    neu(
        "einkommensarten",
        "Haushalte nach Einkommensart",
        dg.balken(arten, "Einkommensarten"),
        ["Einkommensart", "Haushalte"],
        [[n, w] for n, w in arten],
        "Ohne beendete Haushalte.",
    )
    darf_art9 = benutzer is not None and rollen.hat_recht(benutzer, "kunden.besondere_kategorie")
    merkmale = aw.merkmale(darf_art9, stellen)
    if merkmale:
        neu(
            "merkmale",
            "Personen in aktiven Haushalten nach Merkmal",
            dg.balken(merkmale, "Merkmale", farbe=2),
            ["Merkmal", "Personen"],
            [[n, w] for n, w in merkmale],
            "Heutiger Stand. Merkmale der besonderen Kategorie (Art. 9, z. B. Schwerbehindert) "
            "nur mit dem Recht „Angaben der besonderen Kategorie“.",
        )
    auslastung = aw.auslastung(stellen)
    mit_max = [(a.name, a.prozent) for a in auslastung if a.prozent is not None]
    neu(
        "auslastung",
        "Auslastung der Kundengruppen",
        dg.balken(mit_max, "Auslastung", " %", nachkomma=1, maximum=100) if mit_max else "",
        ["Kundengruppe", "Haushalte", "Höchstzahl", "Auslastung"],
        [
            [
                a.name,
                a.belegt,
                a.maximum or "–",
                f"{a.prozent:.1f} %".replace(".", ",") if a.prozent is not None else "–",
            ]
            for a in auslastung
        ],
        "Haushalte ohne beendete im Verhältnis zur Höchstzahl der Gruppe.",
    )
    aktionen = aw.sonderaktionen(z)
    if aktionen:
        neu(
            "sonderaktionen",
            "Sonderaktionen im Zeitraum",
            dg.balken([(a["name"], a["haushalte"]) for a in aktionen], "Sonderaktionen", farbe=1),
            ["Sonderaktion", "Zeitraum", "Haushalte", "Stück"],
            [[a["name"], a["zeitraum"], a["haushalte"], a["stueck"]] for a in aktionen],
        )

    mit_spenden, mit_mitgliedern = _verein(benutzer, stellen)
    if mit_spenden:
        from apps.mitglieder.models import MitgliederEinstellungen
        from apps.spenden.models import Spende

        geld = aw.verlauf(aw.spenden(z, Spende.Art.GELD), z, wert="betrag")
        sach = aw.verlauf(aw.spenden(z, Spende.Art.SACH), z)
        daten = list(zip(beschriftung, geld, strict=True))
        neu(
            "spenden",
            f"Geldspenden je {einheit}",
            dg.saeulen(daten, "Geldspenden", " €", nachkomma=2, farbe=1),
            [einheit, "Geldspenden (Euro)", "Sachspenden (Anzahl)"],
            [
                [n, f"{w:.2f}".replace(".", ","), int(s)]
                for (n, w), s in zip(daten, sach, strict=True)
            ],
            ("Ohne Mitgliedsbeiträge. " if MitgliederEinstellungen.mit_beitraegen() else "")
            + "Die Tabelle zeigt zusätzlich die Zahl der Sachspenden.",
        )
        zwecke = aw.spenden_nach_zweck(z)
        neu(
            "spenden_zweck",
            "Geldspenden nach Zweck",
            dg.balken(zwecke, "Geldspenden nach Zweck", " €", nachkomma=2, farbe=1),
            ["Zweck", "Euro"],
            [[n, f"{w:.2f}".replace(".", ",")] for n, w in zwecke],
            "Mehr als acht Zwecke werden zu „Andere“ zusammengefasst.",
        )
    if mit_mitgliedern:
        linien_neu("mitglieder")
        arten = aw.mitglieder_nach_art(min(heute, z.bis))
        neu(
            "mitglieder_art",
            "Mitglieder nach Art",
            dg.balken(arten, "Mitglieder nach Art", farbe=2),
            ["Art", "Mitglieder"],
            [[n, w] for n, w in arten],
            "Stand am Ende des Zeitraums.",
        )
    return liste


def kennzahlen_kacheln(z: aw.Zeitraum, stellen, heute, benutzer) -> list[tuple[str, str, str]]:
    """Kennzahlen als (Titel, Wert, Erläuterung) für die Kacheln und den Jahresbericht."""
    k = aw.kennzahlen(z, stellen)
    kacheln = [
        ("Abholungen", f"{k.abholungen:,}".replace(",", "."), "im Zeitraum"),
        ("Haushalte", f"{k.haushalte:,}".replace(",", "."), "mindestens einmal abgeholt"),
        (
            "Erreichte Personen",
            f"{k.personen:,}".replace(",", "."),
            "Summe der Haushaltsgrößen je Abholung",
        ),
        ("Bareinnahmen", _euro(k.einnahmen), "laut Kundenkonto"),
        (
            "Aktive Haushalte",
            f"{k.aktive_haushalte:,}".replace(",", "."),
            f"heute, mit {k.aktive_personen:,} Personen".replace(",", "."),
        ),
        ("Neue Kunden", f"{int(k.neue_kunden):,}".replace(",", "."), "im Zeitraum"),
    ]
    if stellen is None:
        kacheln.append(("Anträge", f"{k.antraege:,}".replace(",", "."), "eingegangen"))
    mit_spenden, mit_mitgliedern = _verein(benutzer, stellen)
    if mit_spenden:
        s = aw.spendenzahlen(z)
        kacheln += [
            ("Geldspenden", _euro(s.geld), f"{s.geldspenden} Spenden, {s.spender} Spender gesamt"),
            ("Sachspenden", f"{s.sachspenden:,}".replace(",", "."),
             f"Wert {_euro(s.sachwert)}" if s.sachwert else "im Zeitraum"),
        ]  # fmt: skip
    if mit_mitgliedern:
        from apps.mitglieder.models import MitgliederEinstellungen

        tag = min(heute, z.bis)
        anzahl = sum(n for _, n in aw.mitglieder_nach_art(tag))
        kacheln.append(("Mitglieder", f"{anzahl:,}".replace(",", "."), f"am {tag:%d.%m.%Y}"))
        if MitgliederEinstellungen.mit_beitraegen():
            beitraege = aw.spendenzahlen(z).beitraege
            kacheln.append(("Mitgliedsbeiträge", _euro(beitraege), "eingegangen"))
    return kacheln


def _abfrage_ohne(get, *weglassen) -> str:
    p = get.copy()
    for schluessel in weglassen:
        p.pop(schluessel, None)
    return p.urlencode()


@rollen.recht_erforderlich("statistik.sehen")
def uebersicht(request):
    heute = timezone.localdate()
    wahl, z, vorgaben = _zeitraum(request, heute)
    stellen, auswahl, gewaehlt = _stellen(request)
    # Legenden-Klick (htmx): nur den einen Verlaufs-Abschnitt neu berechnen, nicht die ganze Seite.
    nur = request.GET.get("nur")
    if nur and request.headers.get("HX-Request"):
        teil = linien_abschnitt(nur, z, stellen, request.user, request.GET)
        if teil is not None:
            return render(
                request,
                "statistik/_abschnitt.html",
                {"a": teil, "abfrage": _abfrage_ohne(request.GET, "nur", "csv")},
            )
        return HttpResponse(status=204)  # Abschnitt gibt es nicht (mehr): nichts austauschen
    teile = abschnitte(z, stellen, heute, request.user, get=request.GET)
    csv_teil = request.GET.get("csv")
    if csv_teil:
        teil = next((t for t in teile if t["id"] == csv_teil), None)
        if teil is not None:
            antwort = HttpResponse(content_type="text/csv; charset=utf-8")
            antwort["Content-Disposition"] = (
                f'attachment; filename="statistik-{teil["id"]}-{z.von}-{z.bis}.csv"'
            )
            antwort.write("﻿")
            schreiber = csv.writer(antwort, delimiter=";")
            schreiber.writerow(teil["kopf"])
            schreiber.writerows(teil["zeilen"])
            return antwort
    kacheln = kennzahlen_kacheln(z, stellen, heute, request.user)
    return render(
        request,
        "statistik/uebersicht.html",
        {
            "z": z,
            "wahl": wahl,
            "vorgaben": vorgaben,
            "auswahl": auswahl,
            "gewaehlt": gewaehlt,
            "eingeschraenkt": zugang.stellen(request.user) is not None,
            "kacheln": kacheln,
            "abschnitte": teile,
            "abfrage": request.GET.urlencode(),
            "jahre": list(range(heute.year, heute.year - 6, -1)),
        },
    )


@rollen.recht_erforderlich("statistik.sehen")
def jahresbericht(request):
    """Jahresbericht als PDF für ein Kalenderjahr; Ausgabestelle wie auf der Statistik-Seite."""
    heute = timezone.localdate()
    wert = request.GET.get("jahr", "")
    jahr = int(wert) if wert.isdigit() and 2000 <= int(wert) <= heute.year else heute.year
    z = jb.zeitraum(jahr, heute)
    stellen, _, gewaehlt = _stellen(request)
    teile = abschnitte(z, stellen, heute, request.user)
    kacheln = kennzahlen_kacheln(z, stellen, heute, request.user)
    stelle = stellen[0].name if gewaehlt and stellen else ""
    inhalt = jb.erzeugen(jahr, z, kacheln, teile, stelle)
    return pdf_antwort(inhalt, f"jahresbericht-{jahr}.pdf")


def _verband_wahl(request, heute):
    """Jahr und Stichmonat der Verbandsstatistik (Vorgabe: Juni; vor Juli das Vorjahr)."""
    from apps.statistik import verband

    wert = request.GET.get("jahr", "")
    vorgabe = heute.year if heute.month > 6 else heute.year - 1
    jahr = int(wert) if wert.isdigit() and 2000 <= int(wert) <= heute.year else vorgabe
    monat = request.GET.get("monat", "")
    monat = int(monat) if monat.isdigit() and 1 <= int(monat) <= 12 else 6
    stellen, auswahl, gewaehlt = _stellen(request)
    jetzt, vorher, fragen = verband.fragen(jahr, monat, stellen)
    for f in fragen:
        if f.vergleich:
            for z in f.zeilen:
                z[-1] = "–" if z[-1] is None else f"{z[-1]:+d}".replace("+0", "0")
    return jahr, monat, stellen, auswahl, gewaehlt, jetzt, vorher, fragen


@rollen.recht_erforderlich("statistik.sehen")
def verband(request):
    """Verbandsstatistik: die jährliche Abfrage des Dachverbands aus den aktuellen Zahlen,
    als Seite, CSV (alle Fragen) und PDF."""
    from apps.statistik import verband as vb

    heute = timezone.localdate()
    jahr, monat, stellen, auswahl, gewaehlt, jetzt, vorher, fragen = _verband_wahl(request, heute)
    name = f"verbandsstatistik-{jahr}-{monat:02d}"
    if request.GET.get("format") == "csv":
        antwort = HttpResponse(content_type="text/csv; charset=utf-8")
        antwort["Content-Disposition"] = f'attachment; filename="{name}.csv"'
        antwort.write("﻿")
        schreiber = csv.writer(antwort, delimiter=";")
        for f in fragen:
            schreiber.writerow([f"{f.nummer} {f.text}"])
            schreiber.writerow(f.kopf)
            schreiber.writerows(f.zeilen)
            if f.hinweis:
                schreiber.writerow([f.hinweis])
            schreiber.writerow([])
        return antwort
    if request.GET.get("format") == "pdf":
        from apps.core.pdf import Pdf

        stelle = stellen[0].name if gewaehlt and stellen else ""
        pdf = Pdf(f"Verbandsstatistik {jetzt.name}",
                  f"Stichmonat {jetzt.name}, Vergleich mit {vorher.name}"
                  + (f" · Ausgabestelle {stelle}" if stelle else ""))  # fmt: skip
        for f in fragen:
            pdf.ueberschrift(f"{f.nummer} {f.text}")
            breiten = [0.4, 0.15, 0.15, 0.15, 0.15] if f.vergleich else None
            pdf.tabelle(f.kopf, f.zeilen, breiten=breiten, rechts=range(1, len(f.kopf)))
            if f.hinweis:
                pdf.absatz(f.hinweis, klein=True)
        pdf.ueberschrift("Legende der Stufen")
        legende = [[f"{s:+d}".replace("+0", "0"), t] for s, t in vb.LEGENDE]
        pdf.tabelle(["Stufe", "Bedeutung"], legende, breiten=[0.15, 0.85])
        return pdf_antwort(pdf.erzeugen(), f"{name}.pdf")
    return render(request, "statistik/verband.html", {
        "jahr": jahr, "monat": monat, "jetzt": jetzt, "vorher": vorher, "fragen": fragen,
        "legende": [(f"{s:+d}".replace("+0", "0"), t) for s, t in vb.LEGENDE],
        "monate": list(enumerate(vb.MONATE, start=1)),
        "jahre": list(range(heute.year, heute.year - 6, -1)),
        "auswahl": auswahl, "gewaehlt": gewaehlt,
        "eingeschraenkt": zugang.stellen(request.user) is not None,
        "abfrage": request.GET.urlencode(),
    })  # fmt: skip

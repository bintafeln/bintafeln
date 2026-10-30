"""Das Menü links: Bereiche mit Unterpunkten, je nach Rechten (ADR 0033).

Ein Bereich ist aufgeklappt, wenn die aktuelle Seite darin liegt. Einträge ohne Recht fehlen;
ein Bereich ohne Einträge fehlt ganz.
"""

from django.conf import settings
from django.urls import reverse

from apps.datenimport.ziele import ZIELE
from apps.konten import rollen


def _eintrag(titel, name, *args, extern=False, genau=False):
    """genau: nur diese Adresse ist „aktiv“; „auch“: weitere Adressanfänge, die dazugehören."""
    return {"titel": titel, "url": reverse(name, args=args), "extern": extern, "genau": genau,
            "auch": []}  # fmt: skip


def _liste(art):
    return ("kunden:liste", art)


def menue(request) -> list[dict]:
    b = request.user
    if not b.is_authenticated:
        return []
    from apps.personal.arbeitszeit import darf_stempeln

    darf = rollen.rechte_von(b)

    def sichtbar_machen(eintraege, adressen):
        """Nur Einträge, für die das Konto das Recht hat (None = ohne Recht sichtbar); dieselbe
        Adresse unter mehreren Rechten erscheint nur einmal."""
        sichtbar = []
        for recht, e in eintraege:
            if (recht is None or recht in darf) and e["url"] not in adressen:
                sichtbar.append(e)
                adressen.add(e["url"])
        return sichtbar

    def zahl_von(eintraege):
        # Zahlen an Einträgen stehen zusammengezählt auch am Bereich (zugeklappt sichtbar)
        gezaehlt = [e for e in eintraege if e.get("zahl") is not None]
        if not gezaehlt:
            return {"zahl": None, "zahl_titel": ""}
        return {
            "zahl": sum(e["zahl"] for e in gezaehlt),
            "zahl_titel": ", ".join(f"{e['zahl']} {e['zahl_titel']}" for e in gezaehlt),
        }

    # Bereiche mit Abschnitten: {bereich: {abschnitt: [(recht, eintrag), …]}}. Abschnitt "" steht
    # oben ohne Überschrift. Module hängen sich mit "Bereich" oder "Bereich/Abschnitt" ein.
    inhalt = {
        "Ausgabestelle": {"": [], "Wochenübersicht": [], "Verwaltung": []},
        # Dienstpläne aller Art unter einem Punkt; die Module hängen sich als Abschnitt ein
        "Dienstpläne": {"Ausgabe": [], "Fahrdienst": []},
        "Meine Arbeitszeit": {"": []},
        "Kunden": {"": [], "Anträge und Warteliste": [], "Kundenstamm": []},
        "Verein": {"Mitglieder": [], "Spenden": [], "Adressen": [], "Serienbriefe": [],
                   "Team": []},
        "Auswertungen": {"": []},
    }  # fmt: skip
    # Bereiche, deren Abschnitte sich einzeln auf- und zuklappen (viele Einträge)
    aufklappbar = {"Verein"}

    def dazu(ziel, eintraege, vorn=False):
        titel, _, abschnitt = ziel.partition("/")
        liste = inhalt.setdefault(titel, {}).setdefault(abschnitt, [])
        if vorn:
            liste[:0] = eintraege
        else:
            liste.extend(eintraege)

    # Zuschaltbare Module (ADR 0049): in die passenden Bereiche, Einstellungen weiter unten
    from apps.core import module

    an = module.eingeschaltet()
    modul_einstellungen = []
    for m in module.alle():
        if m.kennung in an and m.menue:
            for titel, eintraege in m.menue(_eintrag):
                if titel.startswith("Einstellungen"):
                    gruppe = titel.partition("/")[2] or "Module"
                    modul_einstellungen.append((gruppe, eintraege))
                else:
                    dazu(titel, eintraege)

    # Ausgabestelle: was die Ausgabestellen täglich brauchen; Module (z. B. Abrechnung) stehen
    # hinter Einlass, Kasse und Kundenliste
    # Die Kundenliste (mit Suche und Ausgabetag) steht nur einmal im Menü: am Einlass unter
    # „Ausgabestelle“, für die Verwaltung unter „Kunden“
    alle_kunden = _eintrag("Kunden einsehen", "kunden:uebersicht", genau=True)
    alle_kunden["auch"] = [reverse("kunden:uebersicht") + "haushalt/"]
    an_der_stelle = "einlass.nutzen" in darf and "kunden.alle_ausgabestellen" not in darf
    if an_der_stelle:
        alle_kunden["titel"] = "Kundenliste"
    dazu("Ausgabestelle", [
        ("einlass.nutzen", _eintrag("Einlass", "ausgabe:empfang", genau=True)),
        ("kasse.sehen", _eintrag("Kasse", "ausgabe:kasse")),
        ("einlass.nachtragen", _eintrag("Abholungen nachtragen", "ausgabe:nachtragen")),
        *([("kunden.liste", alle_kunden)] if an_der_stelle else []),
    ], vorn=True)  # fmt: skip
    dazu("Ausgabestelle/Verwaltung", [
        ("sonderaktionen.verwalten", _eintrag("Sonderaktionen", "ausgabe:sonderaktionen")),
        ("korrekturen.entscheiden", _eintrag("Korrekturwünsche", "ausgabe:korrekturen")),
    ])  # fmt: skip
    if darf_stempeln(b):  # nur, wer selbst stempelt
        dazu("Meine Arbeitszeit", [
            (None, _eintrag("Meine Arbeitszeit", "personal:meine_arbeitszeit")),
        ])  # fmt: skip

    nachrichten = _eintrag("Nachrichten der Ausgabestellen", "kunden:nachrichten")
    if "kunden.nachrichten" in darf:
        from apps.kunden.views_nachrichten import offene

        nachrichten["zahl"] = offene() or None
        nachrichten["zahl_titel"] = "offene Nachrichten"
    verlaengern = _eintrag("Ausweise verlängern", "kunden:verlaengern")
    if "kunden.bearbeiten" in darf:
        from apps.kunden.models import Nachricht

        gemeldet = (Nachricht.objects.filter(anliegen="verlaengern", erledigt_am__isnull=True)
                    .values("kundennummer").distinct().count())  # fmt: skip
        verlaengern["zahl"] = gemeldet or None
        verlaengern["zahl_titel"] = "gemeldete Haushalte"
    dazu("Kunden", [
        *([] if an_der_stelle else [("kunden.liste", alle_kunden)]),
        ("kunden.bearbeiten", _eintrag("Neuer Haushalt", "kunden:haushalt_neu")),
        ("kunden.bearbeiten", verlaengern),
        ("kunden.nachrichten", nachrichten),
    ], vorn=True)  # fmt: skip
    if "antraege.sehen" in darf:
        from apps.antraege.models import Antrag

        antraege = _eintrag("Anträge", "antraege:liste")
        antraege["zahl"] = Antrag.objects.filter(
            status__in=Antrag.OFFEN, papierkorb_am__isnull=True
        ).count()
        antraege["zahl_titel"] = "offene Anträge"
        dazu("Kunden/Anträge und Warteliste", [
            ("antraege.sehen", antraege),
            ("antraege.sehen", _eintrag("Öffentliches Formular", "antrag:start", extern=True)),
        ], vorn=True)  # fmt: skip
    dazu("Kunden/Kundenstamm", [
        ("kunden.zugriffsprotokoll", _eintrag("Zugriffsprotokoll", "kunden:zugriffe")),
    ])  # fmt: skip

    mitglieder = _eintrag("Mitglieder", "mitglieder:liste", genau=True)
    mitglieder["auch"] = [reverse("mitglieder:liste")]  # auch die Seite eines Mitglieds
    dazu("Verein/Mitglieder", [
        ("mitglieder.sehen", mitglieder),
        ("mitglieder.bearbeiten", _eintrag("Neues Mitglied", "mitglieder:neu")),
    ])  # fmt: skip
    dazu("Verein/Spenden", [
        ("spenden.sehen", _eintrag("Spenden", "spenden:liste", genau=True)),
        ("spenden.erfassen", _eintrag("Spende erfassen", "spenden:neu")),
        ("spenden.erfassen", _eintrag("Spenden importieren", "spenden:importieren")),
        ("spenden.bestaetigen", _eintrag("Zuwendungsbestätigungen", "spenden:bestaetigungen")),
        ("spenden.bestaetigen", _eintrag("Dankesbriefe", "spenden:dank")),
        ("spenden.bestaetigen", _eintrag("Belege hochladen", "spenden:belege")),
    ])  # fmt: skip
    adressbuch = _eintrag("Adressbuch", "adressen:liste", genau=True)
    adressbuch["auch"] = [reverse("adressen:liste")]  # auch die Seite einer Adresse
    dazu("Verein/Adressen", [
        ("adressen.sehen", adressbuch),
        ("adressen.bearbeiten", _eintrag("Neue Adresse", "adressen:neu")),
    ])  # fmt: skip
    dazu("Verein/Serienbriefe", [
        ("serienbriefe.erstellen", _eintrag("Serienbrief erstellen", "serienbriefe:erstellen",
                                            genau=True)),
        ("serienbriefe.erstellen", _eintrag("Vorlagen und Versände", "serienbriefe:vorlagen")),
    ])  # fmt: skip
    dazu("Verein/Team", [
        ("mitarbeitende.verwalten", _eintrag("Mitarbeitende", "konten:mitarbeitende")),
        ("personal.sehen", _eintrag("Personal", "personal:liste", genau=True)),
    ])  # fmt: skip
    dazu("Auswertungen", [
        ("statistik.sehen", _eintrag("Statistik", "statistik:uebersicht", genau=True)),
        ("statistik.sehen", _eintrag("Verbandsstatistik", "statistik:verband")),
    ], vorn=True)  # fmt: skip

    bereiche = [
        {"titel": "Start", "eintraege": [_eintrag("Start", "core:start", genau=True)]},
    ]
    for titel, abschnitte in inhalt.items():
        adressen = set()
        teile = [{"titel": a, "eintraege": sichtbar_machen(e, adressen)}
                 for a, e in abschnitte.items()]  # fmt: skip
        teile = [t for t in teile if t["eintraege"]]
        if not teile:
            continue
        alle = [e for t in teile for e in t["eintraege"]]
        b_ = {"titel": titel, "eintraege": alle, **zahl_von(alle)}
        if titel in aufklappbar:
            b_["gruppen"] = teile
        elif len(teile) > 1 or teile[0]["titel"]:
            b_["abschnitte"] = teile
        bereiche.append(b_)

    # Einstellungen in Untermenüs; Module hängen ihre Einträge über "Einstellungen/<Gruppe>" an
    export = "daten.exportieren" if "daten.exportieren" in darf else "daten.importieren"
    gruppen_einstellungen = {
        "Tafel": [
            ("einstellungen.tafel", _eintrag("Tafel und Module", "core:einstellungen", genau=True)),
            ("einstellungen.mail", _eintrag("E-Mail", "core:mail_einstellungen")),
            ("einstellungen.tafel", _eintrag("bintafeln-Verzeichnis", "core:verzeichnis")),
            *([("einstellungen.tafel", _eintrag("Gemeldete Tafeln", "core:verzeichnis_liste"))]
              if settings.VERZEICHNIS_EMPFANG else []),
        ],
        "Kunden": [
            ("einstellungen.kundenstamm",
             _eintrag("Kundenstamm und Zusatzfelder", "kunden:einstellungen")),
            ("einstellungen.listen", _eintrag("Kundengruppen", *_liste("kundengruppen"))),
            ("einstellungen.listen", _eintrag("Einkommensarten", *_liste("einkommensarten"))),
            ("einstellungen.listen", _eintrag("Notiz-Vorlagen", *_liste("notizvorlagen"))),
            ("einstellungen.listen", _eintrag("Dokumentarten", *_liste("dokumentarten"))),
            ("einstellungen.ausweis", _eintrag("Kundenausweis", "kunden:ausweis_gestalten")),
            ("einstellungen.antraege", _eintrag("Anträge", "antraege:einstellungen")),
        ],
        "Ausgabe": [
            # Ausgabestellen pflegen (Anschrift, Zeiten, Ansprechpartner) und ihre Tablet-Konten
            ("kunden.alle_ausgabestellen", _eintrag("Ausgabestellen", "kunden:ausgabestellen")),
            ("mitarbeitende.verwalten", _eintrag("Ausgabestellen-Konten", "konten:stellen")),
            ("einstellungen.ausgabe",
             _eintrag("Ausgabe, Ampel und Beiträge", "ausgabe:einstellungen")),
            ("einstellungen.listen",
             _eintrag("Beitragsfreie Zeiträume", *_liste("beitragsfrei"))),
            ("einstellungen.listen", _eintrag("Sonderausgaben", *_liste("sonderausgaben"))),
        ],
        "Verein": [
            ("einstellungen.listen", _eintrag("Adresskategorien", *_liste("adresskategorien"))),
            ("einstellungen.mitglieder", _eintrag("Mitglieder", "mitglieder:einstellungen")),
            ("einstellungen.spenden",
             _eintrag("Spenden und Zuwendungsbestätigungen", "spenden:einstellungen")),
        ],
        "Dienstpläne": [],
        "Mitarbeitende": [
            ("einstellungen.rollen", _eintrag("Rollen und Rechte", "konten:rollen")),
            ("einstellungen.personal",
             _eintrag("Mitarbeitende und Dokumente", "konten:personal_einstellungen")),
            ("einstellungen.arbeitszeit",
             _eintrag("Arbeitszeit", "personal:arbeitszeit_einstellungen")),
        ],
        "Systemsteuerung": [
            ("system.sicherung", _eintrag("Sicherungen", "core:sicherungen")),
            (export, _eintrag("Export und Zurücklesen", "core:datensicherung")),
            ("system.update", _eintrag("Update", "core:update")),
            *([(None, _eintrag("Daten importieren (CSV, Excel)", "datenimport:start"))]
              if darf & {z.recht for z in ZIELE.values()}
              else []),
            ("einstellungen.tafel", _eintrag("Speicher und Fotos", "core:speicher")),
            ("protokoll.sehen", _eintrag("Änderungsprotokoll", "core:protokoll")),
            ("einstellungen.rollen",
             _eintrag("Anmeldung und Zwei-Faktor", "konten:anmelde_einstellungen")),
            *([(None, _eintrag("Django-Verwaltung", "admin:index"))] if b.is_staff else []),
        ],
    }  # fmt: skip
    for gruppe, eintraege in modul_einstellungen:
        gruppen_einstellungen.setdefault(gruppe, []).extend(eintraege)
    untergruppen = []
    for titel, eintraege in gruppen_einstellungen.items():
        sichtbar = [e for recht, e in eintraege if recht is None or recht in darf]
        if sichtbar:
            untergruppen.append({"titel": titel, "eintraege": sichtbar})
    if untergruppen:
        bereiche.append(
            {
                "titel": "Einstellungen",
                "gruppen": untergruppen,
                "zahl": None,
                "eintraege": [e for g in untergruppen for e in g["eintraege"]],
            }
        )
    from apps.core import papierkorb

    # Nur, wer etwas darin sehen darf (gleiches Recht wie beim Löschen, ADR 0073); die Zahl
    # zählt nur, was seit dem letzten Blick in den Papierkorb neu dazugekommen ist
    sichtbar = papierkorb.sichtbar(b)
    if sichtbar.exists():
        gesehen = b.papierkorb_gesehen_am
        neu = sichtbar.filter(geloescht_am__gt=gesehen).count() if gesehen else sichtbar.count()
        korb = _eintrag("Papierkorb", "core:papierkorb")
        korb.update(zahl=neu or None, zahl_titel="neu im Papierkorb")
        bereiche.append({"titel": "Papierkorb", "eintraege": [korb], "zahl": neu or None,
                         "zahl_titel": korb["zahl_titel"]})  # fmt: skip
    bereiche.append({"titel": "Hilfe", "eintraege": [_eintrag("Hilfe", "core:hilfe")]})
    # „Mein Konto“ öffnet der eigene Name oben rechts

    pfad = request.path
    for bereich in bereiche:
        for e in bereich["eintraege"]:
            e["aktiv"] = pfad == e["url"] if e["genau"] else pfad.startswith(e["url"])
        # „auch“ nur, wenn kein anderer Eintrag die Seite schon genau trifft (z. B. Neuer Haushalt)
        if not any(e["aktiv"] for e in bereich["eintraege"]):
            for e in bereich["eintraege"]:
                e["aktiv"] = any(pfad.startswith(a) for a in e["auch"])
        bereich["offen"] = any(e["aktiv"] for e in bereich["eintraege"])
        bereich["einzeln"] = len(bereich["eintraege"]) == 1
        # Unterpunkte (dritte Ebene) klappen erst auf, wenn man sie wählt
        for gruppe in [*bereich.get("gruppen", []), *bereich.get("abschnitte", [])]:
            gruppe["offen"] = any(e["aktiv"] for e in gruppe["eintraege"])
    return bereiche

"""Das Menü links: Bereiche mit Unterpunkten, je nach Rechten (ADR 0033).

Ein Bereich ist aufgeklappt, wenn die aktuelle Seite darin liegt. Einträge ohne Recht fehlen;
ein Bereich ohne Einträge fehlt ganz.
"""

from django.urls import reverse

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

    def bereich(titel, eintraege):
        """Nur Einträge, für die das Konto das Recht hat (None = ohne Recht sichtbar)."""
        sichtbar = [e for recht, e in eintraege if recht is None or recht in darf]
        if sichtbar:
            # Eine Zahl am Eintrag steht auch am Bereich, damit man sie zugeklappt sieht
            gezaehlt = next((e for e in sichtbar if e.get("zahl") is not None), {})
            bereiche.append({"titel": titel, "eintraege": sichtbar, "zahl": gezaehlt.get("zahl"),
                             "zahl_titel": gezaehlt.get("zahl_titel", "")})  # fmt: skip

    bereiche = [
        {"titel": "Start", "eintraege": [_eintrag("Start", "core:start", genau=True)]},
    ]
    bereich("Ausgabe", [
        ("einlass.nutzen", _eintrag("Einlass", "ausgabe:empfang", genau=True)),
        ("kasse.sehen", _eintrag("Kasse", "ausgabe:kasse")),
        ("sonderaktionen.verwalten", _eintrag("Sonderaktionen", "ausgabe:sonderaktionen")),
        ("korrekturen.entscheiden", _eintrag("Korrekturwünsche", "ausgabe:korrekturen")),
    ])  # fmt: skip
    alle_kunden = _eintrag("Alle Kunden", "kunden:uebersicht", genau=True)
    alle_kunden["auch"] = [reverse("kunden:uebersicht") + "haushalt/"]
    bereich("Kunden", [
        ("kunden.liste", alle_kunden),
        ("kunden.bearbeiten", _eintrag("Neuer Haushalt", "kunden:haushalt_neu")),
        ("kunden.importieren", _eintrag("Kundenstamm importieren", "kunden:import")),
        ("kunden.zugriffsprotokoll", _eintrag("Zugriffsprotokoll", "kunden:zugriffe")),
    ])  # fmt: skip
    if "antraege.sehen" in darf:
        from apps.antraege.models import Antrag

        antraege = _eintrag("Anträge", "antraege:liste")
        antraege["zahl"] = Antrag.objects.filter(
            status__in=Antrag.OFFEN, papierkorb_am__isnull=True
        ).count()
        antraege["zahl_titel"] = "offene Anträge"
        bereich("Anträge", [
            ("antraege.sehen", antraege),
            ("einstellungen.antraege", _eintrag("Formular einstellen", "antraege:einstellungen")),
            ("antraege.sehen", _eintrag("Öffentliches Formular", "antrag:start", extern=True)),
        ])  # fmt: skip
    bereich("Statistik", [("statistik.sehen", _eintrag("Statistik", "statistik:uebersicht"))])
    bereich("Team", [
        ("mitarbeitende.verwalten", _eintrag("Mitarbeitende", "konten:mitarbeitende")),
        ("personal.sehen", _eintrag("Personal", "personal:liste", genau=True)),
        *([(None, _eintrag("Meine Arbeitszeit", "personal:meine_arbeitszeit"))]
          if darf_stempeln(b) else []),
    ])  # fmt: skip
    bereich("Einstellungen", [
        ("einstellungen.tafel", _eintrag("Tafel", "core:einstellungen", genau=True)),
        ("einstellungen.rollen", _eintrag("Rollen und Rechte", "konten:rollen")),
        ("einstellungen.mail", _eintrag("E-Mail", "core:mail_einstellungen")),
        ("einstellungen.kundenstamm",
         _eintrag("Kundenstamm und Zusatzfelder", "kunden:einstellungen")),
        ("einstellungen.listen", _eintrag("Kundengruppen", *_liste("kundengruppen"))),
        ("einstellungen.listen", _eintrag("Ausgabestellen", *_liste("ausgabestellen"))),
        ("einstellungen.listen", _eintrag("Einkommensarten", *_liste("einkommensarten"))),
        ("einstellungen.listen", _eintrag("Notiz-Vorlagen", *_liste("notizvorlagen"))),
        ("einstellungen.listen", _eintrag("Dokumentarten", *_liste("dokumentarten"))),
        ("einstellungen.ausweis", _eintrag("Kundenausweis", "kunden:ausweis_gestalten")),
        ("einstellungen.ausgabe",
         _eintrag("Ausgabe, Ampel und Beiträge", "ausgabe:einstellungen")),
        ("einstellungen.listen", _eintrag("Beitragsfreie Zeiträume", *_liste("beitragsfrei"))),
        ("einstellungen.antraege", _eintrag("Anträge", "antraege:einstellungen")),
        ("einstellungen.personal",
         _eintrag("Mitarbeitende und Dokumente", "konten:personal_einstellungen")),
        ("einstellungen.arbeitszeit",
         _eintrag("Arbeitszeit", "personal:arbeitszeit_einstellungen")),
        ("protokoll.sehen", _eintrag("Änderungsprotokoll", "core:protokoll")),
        ("daten.exportieren" if "daten.exportieren" in darf else "daten.importieren",
         _eintrag("Datensicherung", "core:datensicherung")),
        *([(None, _eintrag("Django-Verwaltung", "admin:index"))] if b.is_staff else []),
    ])  # fmt: skip
    bereiche.append({"titel": "Hilfe", "eintraege": [_eintrag("Hilfe", "core:hilfe")]})
    bereiche.append({"titel": "Mein Konto", "eintraege": [
        _eintrag("Mein Konto", "konten:mein_konto", genau=True),
    ]})  # fmt: skip

    pfad = request.path
    for bereich in bereiche:
        for e in bereich["eintraege"]:
            e["aktiv"] = (pfad == e["url"] if e["genau"] else pfad.startswith(e["url"])) or any(
                pfad.startswith(a) for a in e["auch"]
            )
        bereich["offen"] = any(e["aktiv"] for e in bereich["eintraege"])
        bereich["einzeln"] = len(bereich["eintraege"]) == 1
    return bereiche

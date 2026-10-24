"""Das Menü links: Bereiche mit Unterpunkten, je nach Rolle (keine Mandantenlogik).

Ein Bereich ist aufgeklappt, wenn die aktuelle Seite darin liegt. Einträge ohne Recht fehlen;
ein Bereich ohne Einträge fehlt ganz.
"""

from django.urls import reverse

from apps.konten import rollen
from apps.konten.rollen import darf_mitarbeitende_verwalten


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

    hat = lambda *r: rollen.hat_rolle(b, *r)  # noqa: E731
    admin, buero, ausgabe = hat(rollen.ADMIN), hat(rollen.BUERO), hat(rollen.AUSGABE)
    personal = hat(rollen.ADMIN, rollen.PERSONAL)
    bereiche = [
        {"titel": "Start", "eintraege": [_eintrag("Start", "core:start", genau=True)]},
    ]
    if admin or buero or ausgabe:
        bereiche.append({"titel": "Ausgabe", "eintraege": [
            _eintrag("Einlass", "ausgabe:empfang", genau=True),
            _eintrag("Kasse", "ausgabe:kasse"),
        ]})  # fmt: skip
        kunden = [_eintrag("Alle Kunden", "kunden:uebersicht", genau=True)]
        kunden[0]["auch"] = [reverse("kunden:uebersicht") + "haushalt/"]
        if admin:
            kunden.append(_eintrag("Neuer Haushalt", "kunden:haushalt_neu"))
        if admin or buero:
            kunden.append(_eintrag("Kundenstamm importieren", "kunden:import"))
        if admin:
            kunden.append(_eintrag("Zugriffsprotokoll", "kunden:zugriffe"))
        bereiche.append({"titel": "Kunden", "eintraege": kunden})
    if admin or buero:
        antraege = [_eintrag("Anträge", "antraege:liste")]
        if admin:
            antraege.append(_eintrag("Formular einstellen", "antraege:einstellungen"))
        antraege.append(_eintrag("Öffentliches Formular", "antrag:start", extern=True))
        bereiche.append({"titel": "Anträge", "eintraege": antraege})
    team = []
    if darf_mitarbeitende_verwalten(b):
        team.append(_eintrag("Mitarbeitende", "konten:mitarbeitende"))
    if personal:
        team.append(_eintrag("Personal", "personal:liste", genau=True))
    if darf_stempeln(b):
        team.append(_eintrag("Meine Arbeitszeit", "personal:meine_arbeitszeit"))
    if team:
        bereiche.append({"titel": "Team", "eintraege": team})
    if admin:
        bereiche.append({"titel": "Einstellungen", "eintraege": [
            _eintrag("Tafel", "core:einstellungen", genau=True),
            _eintrag("E-Mail", "core:mail_einstellungen"),
            _eintrag("Kundenstamm und Zusatzfelder", "kunden:einstellungen"),
            _eintrag("Kundengruppen", *_liste("kundengruppen")),
            _eintrag("Ausgabestellen", *_liste("ausgabestellen")),
            _eintrag("Einkommensarten", *_liste("einkommensarten")),
            _eintrag("Notiz-Vorlagen", *_liste("notizvorlagen")),
            _eintrag("Dokumentarten", *_liste("dokumentarten")),
            _eintrag("Kundenausweis", "kunden:ausweis_gestalten"),
            _eintrag("Ausgabe, Ampel und Beiträge", "ausgabe:einstellungen"),
            _eintrag("Beitragsfreie Zeiträume", *_liste("beitragsfrei")),
            _eintrag("Anträge", "antraege:einstellungen"),
            _eintrag("Mitarbeitende und Dokumente", "konten:personal_einstellungen"),
            _eintrag("Arbeitszeit", "personal:arbeitszeit_einstellungen"),
            _eintrag("Änderungsprotokoll", "core:protokoll"),
        ]})  # fmt: skip
        if b.is_staff:
            bereiche[-1]["eintraege"].append(_eintrag("Django-Verwaltung", "admin:index"))
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

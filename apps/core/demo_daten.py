"""Erfundene Daten für die öffentliche Demo (ADR 0022): genug, um Listen, Filter, Auswertungen
und Module wirklich auszuprobieren.

Alles ist erfunden und wird aus festen Namenslisten mit einem festen Startwert erzeugt – nach
jedem Zurücksetzen stehen also dieselben Namen da. Der Kundenstamm entsteht als Dateien im
neutralen Importformat und läuft durch denselben Import wie echte Daten; die übrigen Bereiche
(Adressbuch, Mitglieder, Spenden, Mitarbeitende, Anträge, Tickets, Abrechnung, Serienbriefe,
Fahrdienst, Dienstplan) werden direkt angelegt.
"""

import csv
import datetime as dt
import io
import random
from decimal import Decimal

from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.utils import timezone

from apps.konten import rollen

STARTWERT = 2026
ORT, PLZ = "Musterstadt", "12345"
WOCHENTAGE = ["Mo", "Di", "Mi", "Do", "Fr"]

VORNAMEN_W = ["Alma", "Bente", "Clara", "Dunja", "Elif", "Frida", "Gesa", "Hanna", "Ilka", "Jule",
              "Kira", "Lotta", "Mila", "Nele", "Oda", "Pia", "Romy", "Svea", "Tessa", "Ute",
              "Vera", "Wanda", "Yara", "Zita", "Aylin", "Malin", "Sena", "Thea"]  # fmt: skip
VORNAMEN_M = ["Arne", "Bela", "Cem", "Dario", "Enno", "Falk", "Gero", "Henk", "Ivo", "Jaro",
              "Kalle", "Levi", "Milo", "Nico", "Onno", "Piet", "Rafi", "Sönke", "Tamo", "Ulf",
              "Veit", "Wim", "Yusuf", "Zeno", "Emre", "Jannis", "Luan", "Mats"]  # fmt: skip
NACHNAMEN = ["Abendrot", "Birkenhain", "Dornbusch", "Eichental", "Federwolke", "Ginsterfeld",
             "Haselbach", "Immergrün", "Kieselstein", "Lerchenau", "Mondschein", "Nebelhorn",
             "Ostwind", "Pfauenauge", "Quellgrund", "Rosenhügel", "Sonnenfeld", "Tannenzapf",
             "Uferweide", "Veilchental", "Wiesenthal", "Zaunkönig", "Apfelgarten", "Blaubeer",
             "Distelfink", "Erlenbruch", "Fuchsbau", "Glockenblum", "Heidekraut", "Kranichzug",
             "Lindenblatt", "Morgentau", "Nussbaumer", "Regenbogen", "Silbersee", "Sternthaler",
             "Traumfänger", "Wolkenstein", "Yildirimtal", "Zimtstern"]  # fmt: skip
STRASSEN = ["Ahornweg", "Birkenallee", "Chausseestraße", "Dorfanger", "Elsterweg", "Feldrain",
            "Gartenstraße", "Hasenwinkel", "Im Wiesengrund", "Kastanienring", "Lindenplatz",
            "Mühlenweg", "Nelkenpfad", "Obstwiese", "Parkstraße", "Quellenweg", "Ringstraße",
            "Schulgasse", "Tulpenweg", "Uferpromenade"]  # fmt: skip
EINKOMMEN = ["Bürgergeld", "Rente", "Wohngeld", "Grundsicherung", "Asylbewerberleistungen",
             "geringes Einkommen"]  # fmt: skip
STAATEN = ["deutsch"] * 6 + ["ukrainisch", "syrisch", "türkisch", "polnisch"]
FAMILIENSTAND = ["ledig", "verheiratet", "geschieden", "verwitwet"]

# Kürzel, Name, Ausgabestelle, Wochentag, Uhrzeit, Maximum – MO1 und DI1 stehen schon in den
# Beispieldateien der Dokumentation, die übrigen kommen hier dazu.
GRUPPEN = [
    ("MO1", "Montag früh", "Ausgabestelle Mitte", "Mo", "12:30", 50),
    ("DI1", "Dienstag", "Ausgabestelle Nord", "Di", "14:00", 40),
    ("MO2", "Montag spät", "Ausgabestelle Mitte", "Mo", "14:30", 50),
    ("MI1", "Mittwoch", "Ausgabestelle Mitte", "Mi", "13:00", 50),
    ("DI2", "Dienstag spät", "Ausgabestelle Nord", "Di", "15:30", 40),
    ("DO1", "Donnerstag", "Ausgabestelle Nord", "Do", "14:00", 45),
    ("MI2", "Mittwoch Süd", "Ausgabestelle Süd", "Mi", "10:00", 40),
    ("FR1", "Freitag", "Ausgabestelle Süd", "Fr", "11:00", 50),
]
NEUE_GRUPPEN = GRUPPEN[2:]

FIRMEN = ["Bäckerei Kornblume", "Supermarkt Frischekorb", "Gemüsehof Sonnenacker",
          "Metzgerei Landlust", "Getränke Quellfrisch", "Biomarkt Grünes Blatt",
          "Großhandel Marktplatz", "Konditorei Zuckerwerk", "Molkerei Wiesenglück",
          "Obsthof Apfeltraum", "Drogerie Seifenblase", "Autohaus Radwechsel",
          "Sparkasse Musterstadt", "Stadtwerke Musterstadt", "Kirchengemeinde St. Beispiel",
          "Sportverein Blau-Weiß Musterstadt", "Lions Club Musterstadt", "Apotheke am Markt",
          "Druckerei Schwarz auf Weiß", "Gärtnerei Blütenpracht", "Stiftung Gute Tat",
          "Schreinerei Holzwurm", "Gasthaus Zur Linde", "Wochenmarkt-Verein Musterstadt",
          "Fahrradladen Kettenglück"]  # fmt: skip
KATEGORIEN = ["Lebensmittelspender", "Geldspender", "Lieferant", "Partner", "Presse"]


def _datum(tag: dt.date) -> str:
    return f"{tag:%d.%m.%Y}"


def _person(zufall) -> tuple[str, str, str]:
    """(Anrede, Vorname, Nachname) – erfunden."""
    if zufall.random() < 0.5:
        return "Frau", zufall.choice(VORNAMEN_W), zufall.choice(NACHNAMEN)
    return "Herr", zufall.choice(VORNAMEN_M), zufall.choice(NACHNAMEN)


def _anschrift(zufall) -> str:
    return f"{zufall.choice(STRASSEN)} {zufall.randint(1, 48)}"


def _letzter(heute: dt.date, wochentag: str, wochen: int = 0) -> dt.date:
    """Der letzte Tag mit diesem Wochentag vor heute, ``wochen`` Wochen weiter zurück."""
    zurueck = (heute.weekday() - WOCHENTAGE.index(wochentag)) % 7 or 7
    return heute - dt.timedelta(days=zurueck + 7 * wochen)


def _anhaengen(dateien: dict, name: str, zeilen: list[dict]) -> None:
    """Hängt Zeilen an eine Beispieldatei an (Spalten wie in deren Kopfzeile)."""
    text = dateien[name].decode("utf-8-sig")
    spalten = text.splitlines()[0].split(";")
    puffer = io.StringIO()
    schreiber = csv.DictWriter(puffer, fieldnames=spalten, delimiter=";", lineterminator="\n",
                               restval="")  # fmt: skip
    schreiber.writerows(zeilen)
    dateien[name] = (text.rstrip("\n") + "\n" + puffer.getvalue()).encode("utf-8")


def kundenstamm(dateien: dict, heute: dt.date) -> dict:
    """Ergänzt die Beispieldateien des Importformats: weitere Kundengruppen und je Gruppe 30 bis
    50 Haushalte mit Personen und Abholungen, dazu gesperrte, pausierte und beendete Haushalte
    und solche mit abgelaufenem Ausweis."""
    zufall = random.Random(STARTWERT)  # noqa: S311 – Beispieldaten, kein Geheimnis
    dateien = dict(dateien)
    _anhaengen(dateien, "kundengruppen.csv", [
        {"kuerzel": k, "name": n, "ausgabestelle": s, "wochentage": t, "uhrzeit": u,
         "maximum": m, "aktiv": "ja"} for k, n, s, t, u, m in NEUE_GRUPPEN
    ])  # fmt: skip
    haushalte, personen, abholungen, sperren, bemerkungen = [], [], [], [], []
    nummer = 2000
    for kuerzel, _, stelle, tag, uhrzeit, maximum in GRUPPEN:
        for _ in range(zufall.randint(30, min(50, maximum) - 3)):
            nummer += 1
            kn = str(nummer)
            anrede, vorname, nachname = _person(zufall)
            wurf = zufall.random()
            status = "beendet" if wurf < 0.03 else "pausiert" if wurf < 0.07 else "aktiv"
            abgelaufen = status == "aktiv" and zufall.random() < 0.05
            ausweis = (heute - dt.timedelta(days=zufall.randint(5, 90)) if abgelaufen
                       else heute + dt.timedelta(days=zufall.randint(20, 400)))  # fmt: skip
            kommt = status == "aktiv" and not abgelaufen
            besuche = [_letzter(heute, tag, w) for w in range(8) if zufall.random() < 0.75]
            besuche = besuche if kommt else []
            stunde, minute = (int(x) for x in uhrzeit.split(":"))
            for datum in besuche:
                zeit = dt.time(stunde + zufall.randint(0, 1), (minute + zufall.randint(0, 29)) % 60)
                abholungen.append({
                    "kundennummer": kn, "datum": _datum(datum), "uhrzeit": f"{zeit:%H:%M}",
                    "beitrag": "2,00", "ausgabestelle": stelle, "eingetragen_von": "Anton Ausgabe",
                })  # fmt: skip
            konto = zufall.choice(["0,00"] * 8 + ["2,00", "-2,00", "-4,00"])
            haushalte.append({
                "kundennummer": kn, "nachname": nachname, "vorname": vorname, "anrede": anrede,
                "geburtsdatum": _datum(dt.date(zufall.randint(1940, 2002), zufall.randint(1, 12),
                                               zufall.randint(1, 28))),
                "staatsangehoerigkeit": zufall.choice(STAATEN),
                "familienstand": zufall.choice(FAMILIENSTAND), "status": status,
                "kundengruppe": kuerzel, "ausgabestelle": stelle,
                "kunde_seit": _datum(heute - dt.timedelta(days=zufall.randint(60, 1500))),
                "ausweis_gueltig_bis": _datum(ausweis),
                "letzter_besuch": _datum(max(besuche)) if besuche else "",
                "einkommensart": zufall.choice(EINKOMMEN), "strasse": _anschrift(zufall),
                "plz": PLZ, "ort": ORT,
                "telefon": (f"0000 {zufall.randint(100000, 999999)}"
                            if zufall.random() < 0.6 else ""),
                "email": (f"{vorname}.{nachname}@example.org".lower()
                          if zufall.random() < 0.3 else ""),
                "zusatz_schwerbehindert": "ja" if zufall.random() < 0.08 else "nein",
                "kontostand": konto if status == "aktiv" else "0,00",
            })  # fmt: skip
            for i in range(zufall.choice([0, 0, 1, 1, 2, 3, 4])):
                weiblich = zufall.random() < 0.5
                kind = i > 0 or zufall.random() < 0.4
                jahr = heute.year - (zufall.randint(1, 17) if kind else zufall.randint(20, 75))
                personen.append({
                    "kundennummer": kn, "nachname": nachname,
                    "vorname": zufall.choice(VORNAMEN_W if weiblich else VORNAMEN_M),
                    "anrede": "" if kind else ("Frau" if weiblich else "Herr"),
                    "geburtsdatum": _datum(dt.date(jahr, zufall.randint(1, 12),
                                                   zufall.randint(1, 28))),
                    "staatsangehoerigkeit": haushalte[-1]["staatsangehoerigkeit"],
                    "zusatz_schwerbehindert": "nein",
                })  # fmt: skip
            if kommt and zufall.random() < 0.04:
                sperren.append({
                    "kundennummer": kn, "von": _datum(heute - dt.timedelta(days=10)),
                    "bis": _datum(heute + dt.timedelta(days=20)),
                    "begruendung": "Erfundene Beispielsperre", "eingetragen_von": "Berta Büro",
                })  # fmt: skip
            if zufall.random() < 0.06:
                bemerkungen.append({
                    "kundennummer": kn,
                    "datum": _datum(heute - dt.timedelta(days=zufall.randint(3, 200))),
                    "text": zufall.choice([
                        "Kommt meist mit Rollator, bitte Tür aufhalten.",
                        "Spricht wenig Deutsch, Tochter übersetzt.",
                        "Hat um einen späteren Termin gebeten.",
                        "Allergie in der Familie – keine Nüsse einpacken.",
                    ]),
                    "verfasst_von": "Berta Büro",
                })  # fmt: skip
    _anhaengen(dateien, "haushalte.csv", haushalte)
    _anhaengen(dateien, "personen.csv", personen)
    _anhaengen(dateien, "abholungen.csv", abholungen)
    _anhaengen(dateien, "sperren.csv", sperren)
    _anhaengen(dateien, "bemerkungen.csv", bemerkungen)
    return dateien


# --- Mitarbeitende ------------------------------------------------------------------------------

# Benutzername, Vorname, Nachname, Rollen – alles erfunden; „demo-“ kennzeichnet Demo-Konten.
TEAM = [
    ("demo-ehrenamt-01", "Clara", "Morgentau", [rollen.AUSGABE]),
    ("demo-ehrenamt-02", "Enno", "Silbersee", [rollen.AUSGABE]),
    ("demo-ehrenamt-03", "Hanna", "Lindenblatt", [rollen.AUSGABE]),
    ("demo-ehrenamt-04", "Ivo", "Fuchsbau", [rollen.AUSGABE]),
    ("demo-ehrenamt-05", "Jule", "Regenbogen", [rollen.AUSGABE]),
    ("demo-ehrenamt-06", "Kalle", "Nussbaumer", [rollen.AUSGABE]),
    ("demo-ehrenamt-07", "Lotta", "Heidekraut", [rollen.AUSGABE]),
    ("demo-ehrenamt-08", "Milo", "Kranichzug", [rollen.AUSGABE]),
    ("demo-ehrenamt-09", "Nele", "Blaubeer", [rollen.AUSGABE, rollen.BUERO]),
    ("demo-ehrenamt-10", "Onno", "Sternthaler", [rollen.BUERO]),
    ("demo-ehrenamt-11", "Pia", "Apfelgarten", [rollen.BUERO]),
    ("demo-ehrenamt-12", "Rafi", "Distelfink", [rollen.FAHRER]),
    ("demo-ehrenamt-13", "Svea", "Erlenbruch", [rollen.FAHRER]),
    ("demo-ehrenamt-14", "Tamo", "Wolkenstein", [rollen.FAHRER, rollen.AUSGABE]),
    ("demo-ehrenamt-15", "Ute", "Glockenblum", [rollen.PERSONAL]),
]


def team() -> list:
    """Weitere erfundene Mitarbeitende (Anmeldung mit dem Demo-Passwort), mit Stammdaten."""
    from apps.konten.models import Stammdaten

    zufall = random.Random(STARTWERT + 1)  # noqa: S311
    konten = []
    for name, vorname, nachname, namen in TEAM:
        b = get_user_model().objects.create_user(
            username=name, password=settings.DEMO_PASSWORT, first_name=vorname,
            last_name=nachname, email=f"{name}@example.org",
        )  # fmt: skip
        b.groups.set(Group.objects.filter(name__in=namen))
        Stammdaten.objects.create(
            benutzer=b, strasse=_anschrift(zufall), plz=PLZ, ort=ORT,
            eintritt=dt.date(zufall.randint(2018, 2025), zufall.randint(1, 12), 1),
            fs_klassen="B" if rollen.FAHRER in namen else "",
        )  # fmt: skip
        konten.append(b)
    return konten


# --- Adressbuch, Mitglieder, Spenden ------------------------------------------------------------


def adressen_mitglieder_spenden(heute: dt.date) -> None:
    from apps.adressen.models import Adresse, AdressKategorie
    from apps.core import auswahl
    from apps.mitglieder.models import Mitglied, MitgliederEinstellungen
    from apps.spenden.models import Spende

    zufall = random.Random(STARTWERT + 2)  # noqa: S311
    kategorien = {n: AdressKategorie.objects.get_or_create(name=n)[0] for n in KATEGORIEN}
    firmen = []
    for name in FIRMEN:
        anrede, vorname, nachname = _person(zufall)
        kurz = "".join(c for c in name.lower() if c.isalpha())[:18]
        a = Adresse.objects.create(
            art=Adresse.Art.ORGANISATION, organisation=name,
            ansprechperson=f"{anrede} {vorname} {nachname}", strasse=_anschrift(zufall),
            plz=PLZ, ort=ORT, telefon=f"0000 {zufall.randint(100000, 999999)}",
            email=f"kontakt@{kurz}.example.org",
            einwilligung_post=heute - dt.timedelta(days=zufall.randint(30, 900)),
        )  # fmt: skip
        a.kategorien.set(zufall.sample(list(kategorien.values()), zufall.randint(1, 2)))
        firmen.append(a)
    leute = []
    for _ in range(45):
        anrede, vorname, nachname = _person(zufall)
        a = Adresse.objects.create(
            art=Adresse.Art.PERSON, anrede=anrede, vorname=vorname, nachname=nachname,
            geburtsdatum=dt.date(zufall.randint(1945, 1998), zufall.randint(1, 12),
                                 zufall.randint(1, 28)),
            strasse=_anschrift(zufall), plz=PLZ, ort=ORT,
            mobil=f"0000 {zufall.randint(1000000, 9999999)}",
            email=f"{vorname}.{nachname}{zufall.randint(1, 99)}@example.org".lower(),
            einwilligung_email=heute - dt.timedelta(days=zufall.randint(30, 900)),
        )  # fmt: skip
        if zufall.random() < 0.4:
            a.kategorien.add(kategorien["Geldspender"])
        leute.append(a)
    for i, a in enumerate(leute[:40], start=1):
        ausgetreten = i % 13 == 0
        eintritt = dt.date(zufall.randint(2012, heute.year - 1), zufall.randint(1, 12), 1)
        Mitglied.objects.create(
            adresse=a, nummer=str(i), art=zufall.choice(auswahl.MITGLIEDSARTEN), eintritt=eintritt,
            austritt=heute - dt.timedelta(days=zufall.randint(30, 300)) if ausgetreten else None,
            austrittsgrund="Kündigung" if ausgetreten else "",
            jahresbeitrag=Decimal(zufall.choice(["24.00", "36.00", "60.00"])),
            zahlweise="jährlich", zahlungsart=zufall.choice(auswahl.ZAHLUNGSARTEN),
        )  # fmt: skip
    e = MitgliederEinstellungen.laden()
    e.naechste_nummer = 41
    e.save()
    for i in range(80):
        sach = i % 5 == 0
        spender = zufall.choice(firmen if sach or zufall.random() < 0.4 else leute)
        datum = heute - dt.timedelta(days=zufall.randint(1, 720))
        if sach:
            Spende.objects.create(
                art=Spende.Art.SACH, adresse=spender, datum=datum,
                betrag=Decimal(zufall.randint(20, 400)),
                beschreibung=zufall.choice(["Backwaren vom Vortag", "Obst und Gemüse",
                                            "Molkereiprodukte", "Konserven", "Getränke"]),
                menge=Decimal(zufall.randint(2, 30)), einheit="Kisten",
                eingetragen_von="demo-buero",
            )  # fmt: skip
        else:
            Spende.objects.create(
                art=Spende.Art.GELD, adresse=spender, datum=datum,
                betrag=Decimal(zufall.choice([10, 20, 25, 50, 50, 100, 150, 250, 500])),
                zahlungsweg=zufall.choice(["Überweisung", "Überweisung", "Bar", "Lastschrift"]),
                zweck=zufall.choice(["", "", "Weihnachtsaktion", "Kühlfahrzeug", "Schulranzen"]),
                belegnummer=f"DEMO-{i:03d}", eingetragen_von="demo-buero",
                bedankt_am=datum + dt.timedelta(days=5) if zufall.random() < 0.5 else None,
            )  # fmt: skip


# --- Anträge und Warteliste ---------------------------------------------------------------------


def antraege(heute: dt.date) -> None:
    from apps.antraege.models import Antrag, AntragAnmerkung, AntragPerson
    from apps.warteliste.models import Termin, Wartestand

    zufall = random.Random(STARTWERT + 3)  # noqa: S311
    jetzt = timezone.now()
    termin = Termin.objects.create(
        datum=heute + dt.timedelta(days=9), von=dt.time(10, 0), bis=dt.time(12, 0),
        anmerkung="Anmeldung im Büro (Beispiel)",
    )  # fmt: skip
    stand = Wartestand.Status
    plan = (
        [(Antrag.Status.NEU, stand.NEU)] * 6
        + [(Antrag.Status.IN_BEARBEITUNG, stand.WARTEND)] * 8
        + [(Antrag.Status.IN_BEARBEITUNG, stand.EINGELADEN)] * 5
        + [(Antrag.Status.ERLEDIGT, stand.ERSCHIENEN)] * 4
        + [(Antrag.Status.ABGELEHNT, None)] * 2
    )
    for i, (status, wartestatus) in enumerate(plan):
        anrede, vorname, nachname = _person(zufall)
        eingang = jetzt - dt.timedelta(days=zufall.randint(1, 80), hours=zufall.randint(0, 9))
        a = Antrag.objects.create(
            eingegangen_am=eingang, status=status, anrede=anrede, vorname=vorname,
            nachname=nachname, art=Antrag.Art.VERLAENGERUNG if i % 9 == 4 else Antrag.Art.NEU,
            sprache=zufall.choice(["de", "de", "de", "en", "uk", "ar", "tr"]),
            geburtsdatum=dt.date(zufall.randint(1950, 2003), zufall.randint(1, 12),
                                 zufall.randint(1, 28)),
            strasse=_anschrift(zufall), plz=PLZ, ort=ORT,
            telefon=f"0000 {zufall.randint(100000, 999999)}",
            email=f"{vorname}.{nachname}{i}@example.org".lower(),
            familienstand=zufall.choice(FAMILIENSTAND),
            staatsangehoerigkeit=zufall.choice(STAATEN),
            wochentage=zufall.choice(["Mo", "Di, Do", "Mi", "Fr", ""]),
            ausgabestelle=zufall.choice(["Ausgabestelle Mitte", "Ausgabestelle Nord",
                                         "Ausgabestelle Süd", ""]),
            datenschutz_bestaetigt=True,
            abgeschlossen_am=eingang + dt.timedelta(days=12)
            if status in (Antrag.Status.ERLEDIGT, Antrag.Status.ABGELEHNT) else None,
            nachricht="Wir sind neu in Musterstadt." if i % 6 == 0 else "",
        )  # fmt: skip
        for _ in range(zufall.choice([0, 0, 1, 2, 3])):
            AntragPerson.objects.create(
                antrag=a, vorname=zufall.choice(VORNAMEN_W + VORNAMEN_M), nachname=nachname,
                geburtsdatum=dt.date(heute.year - zufall.randint(2, 60), zufall.randint(1, 12),
                                     zufall.randint(1, 28)),
            )  # fmt: skip
        if status == Antrag.Status.ABGELEHNT:
            AntragAnmerkung.objects.create(antrag=a, text="Wohnort außerhalb des Einzugsgebiets.",
                                           von="Berta Büro")  # fmt: skip
        if wartestatus:
            Wartestand.objects.update_or_create(antrag=a, defaults={
                "status": wartestatus,
                "termin": termin if wartestatus == stand.EINGELADEN else None,
                "eingeladen_am": jetzt - dt.timedelta(days=2)
                if wartestatus == stand.EINGELADEN else None,
            })  # fmt: skip


# --- Tickets, Abrechnung, Serienbriefe ----------------------------------------------------------

TICKETS = [
    (
        "Technik und Geräte",
        "Kühltruhe 2 brummt laut",
        "Seit Montag sehr laut, kühlt aber noch.",
        "in_arbeit",
        ["Techniker kommt am Donnerstag."],
    ),
    (
        "Technik und Geräte",
        "Waage am Einlass zeigt nichts an",
        "Batterie getauscht, hilft nicht.",
        "offen",
        [],
    ),
    (
        "Technik und Geräte",
        "Drucker für Ausweise zieht schief ein",
        "Jede dritte Karte verrutscht.",
        "erledigt",
        ["Walze gereinigt, läuft wieder."],
    ),
    (
        "Lager",
        "Regal 4 wackelt",
        "Unteres Brett hat sich gelöst.",
        "offen",
        ["Bitte bis zur Reparatur nichts Schweres einlagern."],
    ),
    ("Lager", "Zu wenig Klappkisten", "Für Freitag fehlen etwa 20 Kisten.", "in_arbeit", []),
    (
        "Lager",
        "Palette Nudeln läuft bald ab",
        "Mindesthaltbarkeit Ende des Monats.",
        "erledigt",
        ["Am Mittwoch komplett ausgegeben."],
    ),
    ("Gebäude", "Licht im Flur flackert", "Zweite Lampe von links.", "offen", []),
    (
        "Gebäude",
        "Heizung im Büro bleibt kalt",
        "Thermostat reagiert nicht.",
        "in_arbeit",
        ["Hausverwaltung ist informiert."],
    ),
    (
        "Gebäude",
        "Türklingel am Hintereingang defekt",
        "Lieferanten klopfen ans Fenster.",
        "offen",
        [],
    ),
    ("Fahrzeuge", "Transporter: Ölwechsel fällig", "Anzeige leuchtet seit gestern.", "offen", []),
]


def tickets(konten: dict) -> None:
    from apps.tickets.models import Kategorie, Kommentar, Ticket

    buero = Group.objects.get(name=rollen.BUERO)
    kategorien = {}
    for i, (name, text) in enumerate([
        ("Technik und Geräte", "Kühlung, Waagen, Drucker, Kassen"),
        ("Lager", "Regale, Kisten, Ordnung, Haltbarkeit"),
        ("Gebäude", "Licht, Heizung, Türen, Reinigung"),
        ("Fahrzeuge", "Transporter, Kühlfahrzeug, Anhänger"),
    ]):  # fmt: skip
        k = Kategorie.objects.create(name=name, beschreibung=text, reihenfolge=i + 1)
        k.rollen.add(buero)
        kategorien[name] = k
    kategorien["Technik und Geräte"].personen.add(konten["demo-fest"])
    melder = [konten["demo-ausgabe"], konten["demo-fest"], konten["demo-buero"]]
    for i, (kategorie, titel, text, status, antworten) in enumerate(TICKETS):
        t = Ticket.objects.create(
            kategorie=kategorien[kategorie], titel=titel, beschreibung=text, status=status,
            erstellt_von=melder[i % 3],
            zustaendig=konten["demo-buero"] if status != Ticket.Status.OFFEN else None,
            erledigt_am=timezone.now() if status == Ticket.Status.ERLEDIGT else None,
        )  # fmt: skip
        for antwort in antworten:
            Kommentar.objects.create(ticket=t, von=konten["demo-buero"], text=antwort)


def abrechnung(konten: dict, heute: dt.date) -> None:
    from apps.abrechnung import ablauf
    from apps.abrechnung.models import Posten
    from apps.kunden.models import Ausgabestelle

    zufall = random.Random(STARTWERT + 4)  # noqa: S311
    diesen = ablauf.monatsanfang(heute)
    for stelle in Ausgabestelle.objects.filter(name__startswith="Ausgabestelle").order_by("name"):
        for zurueck in (2, 1, 0):
            monat = ablauf.verschieben(diesen, -zurueck)
            abr = ablauf.holen(stelle, monat)
            for _ in range(zufall.randint(2, 5)):
                art, empfaenger = zufall.choice([
                    ("Reinigungsmittel", "Drogerie Seifenblase"),
                    ("Tüten und Verpackung", "Großhandel Marktplatz"),
                    ("Kaffee und Getränke fürs Team", "Supermarkt Frischekorb"),
                    ("Kraftstoff", "Tankstelle am Ring"),
                    ("Büromaterial", "Schreibwaren Federkiel"),
                ])  # fmt: skip
                Posten.objects.create(
                    abrechnung=abr, datum=monat + dt.timedelta(days=zufall.randint(1, 26)),
                    betrag=Decimal(zufall.randint(400, 6500)) / 100, art=art, empfaenger=empfaenger,
                    eingetragen_von="demo-ausgabe",
                )  # fmt: skip
            if zurueck:
                ablauf.einreichen(abr, konten["demo-ausgabe"], "Erfundene Beispielabrechnung")
            if zurueck == 2:
                ablauf.bestaetigen(abr, konten["demo-buero"])


def serienbriefe() -> None:
    from apps.serienbriefe.models import Vorlage

    Vorlage.objects.create(
        name="Einladung zur Mitgliederversammlung",
        betreff="Einladung zur Mitgliederversammlung",
        text="<p>{anrede},</p><p>wir laden Sie herzlich zu unserer jährlichen "
             "Mitgliederversammlung ein. Sie findet im Gemeindesaal am Lindenplatz statt.</p>"
             "<p>Auf der Tagesordnung stehen der Bericht des Vorstands, der Kassenbericht und "
             "die Wahl des Vorstands.</p><p>Mit freundlichen Grüßen<br>Ihr Tafel-Team</p>",
    )  # fmt: skip
    Vorlage.objects.create(
        name="Dank an unsere Unterstützer",
        betreff="Danke für Ihre Unterstützung",
        text="<p>{anrede},</p><p>ohne Menschen und Betriebe wie Sie gäbe es unsere Tafel "
             "nicht. Im vergangenen Jahr konnten wir jede Woche mehrere hundert Haushalte in "
             "Musterstadt mit Lebensmitteln versorgen.</p><p>Dafür sagen wir herzlich Danke!"
             "</p><p>Mit freundlichen Grüßen<br>Ihr Tafel-Team</p>",
    )  # fmt: skip


# --- Fahrdienst und Dienstplan ------------------------------------------------------------------


def dienstplaene(heute: dt.date) -> None:
    """Beispielpläne der beiden Module (dieselben wie der Knopf „Beispiel anlegen“), dazu je ein
    Ausfall in der kommenden Woche, damit man Ersatz eintragen kann."""
    from apps.dienstplan import beispiel as dienstplan_beispiel
    from apps.dienstplan.models import Ausfall as DienstAusfall
    from apps.dienstplan.models import Besetzung as DienstBesetzung
    from apps.fahrdienst import beispiel as fahrdienst_beispiel
    from apps.fahrdienst.models import Ausfall as FahrAusfall
    from apps.fahrdienst.models import Besetzung as FahrBesetzung

    fahrdienst_beispiel.anlegen(seed=STARTWERT)
    dienstplan_beispiel.anlegen(seed=STARTWERT)
    von, bis = heute + dt.timedelta(days=2), heute + dt.timedelta(days=8)
    fahrer = FahrBesetzung.objects.order_by("pk").first()
    if fahrer:
        FahrAusfall.objects.create(person=fahrer.person, von=von, bis=bis, grund="krank",
                                   eingetragen_von="demo-buero")  # fmt: skip
    helfer = DienstBesetzung.objects.order_by("pk").first()
    if helfer:
        DienstAusfall.objects.create(helfer=helfer.helfer, von=von, bis=bis, grund="urlaub",
                                     eingetragen_von="demo-buero")  # fmt: skip

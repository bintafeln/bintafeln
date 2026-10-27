"""Was sich importieren lässt (ADR 0078): je Ziel die Felder, die Prüfung der Werte, der
Bestand zum Abgleich und das Übernehmen.

Der Kundenstamm hat eigene Regeln (Importformat, ``apps.kunden.importieren``): Seine Tabellen
werden nach der Zuordnung in das neutrale Format umgeschrieben und dort geprüft.
"""

import csv
import io
import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import ProtectedError

from apps.datenimport.abgleich import Bestandseintrag, Treffer, abgleichen
from apps.datenimport.zuordnung import Art, Feld, normalisieren
from apps.kunden import werte as wertlesen

FEHLER, WARNUNG = "fehler", "warnung"


def _datum_text(d) -> str:
    return d.strftime("%d.%m.%Y") if d else ""


def _liste(text: str) -> list[str]:
    return [t.strip() for t in re.split(r"[,;/|\n]", text or "") if t.strip()]


class Ziel:
    kennung = ""
    titel = ""
    recht = ""
    beschreibung = ""
    aktionen: list[tuple[str, str]] = [("behalten", "behalten")]
    zurueck = ("core:start", "Start")  # Seite nach dem Übernehmen

    def arten(self) -> list[Art]:
        raise NotImplementedError

    def art(self, schluessel) -> Art:
        return next((a for a in self.arten() if a.schluessel == schluessel), self.arten()[0])

    # --- Werte prüfen -----------------------------------------------------------------

    def bereinigen(self, art: Art, zeilen: list[tuple[int, dict]], tabelle: str):
        """Prüft jede Zeile nach den Feldtypen. Liefert (Sätze, Meldungen); Zeilen mit
        Fehlern (leere Pflichtangabe) werden ausgelassen. Meldungen nennen keine Inhalte."""
        saetze, meldungen = [], []

        def melden(stufe, nummer, text):
            meldungen.append({"stufe": stufe, "tabelle": tabelle, "zeile": nummer, "text": text})

        for nummer, roh in zeilen:
            if not any(roh.values()):
                continue
            werte, fehler = {}, False
            for f in art.felder:
                if f.schluessel not in roh:
                    continue
                wert = (roh.get(f.schluessel) or "").strip()
                if f.pflicht and not wert:
                    melden(
                        FEHLER,
                        nummer,
                        f"Pflichtangabe „{f.bezeichnung}“ ist leer; Zeile wird ausgelassen.",
                    )
                    fehler = True
                    continue
                wert = self.wert(f, wert, lambda text, n=nummer: melden(WARNUNG, n, text))
                if f.laenge and len(wert) > f.laenge:
                    melden(WARNUNG, nummer, f"„{f.bezeichnung}“ ist zu lang und wird gekürzt.")
                    wert = wert[: f.laenge]
                werte[f.schluessel] = wert
            for f in art.felder:
                if f.pflicht and f.schluessel not in roh:
                    fehler = True
            if not fehler:
                saetze.append({"zeile": nummer, "werte": werte})
        return saetze, meldungen

    def wert(self, f: Feld, wert: str, warnen) -> str:
        if not wert:
            return ""
        if f.typ == "datum":
            try:
                return _datum_text(wertlesen.datum(wert[:10] if "-" in wert[:10] else wert))
            except wertlesen.UngueltigerWert:
                warnen(f"„{f.bezeichnung}“ ist kein Datum und bleibt leer.")
                return ""
        if f.typ == "janein":
            try:
                return "ja" if wertlesen.ja_nein(wert) else "nein"
            except wertlesen.UngueltigerWert:
                warnen(f"„{f.bezeichnung}“ ist kein Ja/Nein-Wert und bleibt leer.")
                return ""
        if f.typ == "email":
            try:
                validate_email(wert)
            except ValidationError:
                warnen(f"„{f.bezeichnung}“ ist keine gültige E-Mail-Adresse und bleibt leer.")
                return ""
            return wert.lower()
        if f.typ == "telefon" and not wert.startswith(("0", "+")) and wert[:1].isdigit():
            warnen(f"„{f.bezeichnung}“ beginnt nicht mit 0 oder + (führende 0 verloren?).")
        return " ".join(wert.split()) if f.typ != "langtext" else wert

    # --- Abgleich und Übernehmen ------------------------------------------------------

    def bestand(self, verwalter) -> list[Bestandseintrag]:
        raise NotImplementedError

    def treffer_finder(self, bestand):
        raise NotImplementedError

    def name(self, werte) -> str:
        return werte.get("name", "")

    def schluessel(self, werte) -> str:
        return normalisieren(self.name(werte))

    def vergleichsfelder(self) -> list[tuple[str, str]]:
        return [(f.schluessel, f.bezeichnung) for f in self.arten()[0].felder]

    def fehlt_ausnehmen(self, verwalter) -> set[str]:
        return set()

    def planen(self, saetze, verwalter):
        bestand = self.bestand(verwalter)
        return abgleichen(
            saetze,
            bestand,
            felder=self.vergleichsfelder(),
            treffer=self.treffer_finder(bestand),
            name=self.name,
            schluessel=self.schluessel,
            fehlt_ausnehmen=self.fehlt_ausnehmen(verwalter),
        )

    def anwenden(self, entscheidung, verwalter) -> list[str]:
        raise NotImplementedError


def _name_treffer(bestand, schluessel_fn):
    """Treffer über den genauen Namen; sonst über einen sehr ähnlichen (unsicher)."""
    import difflib

    genau = {}
    for b in bestand:
        genau.setdefault(normalisieren(b.name), b)

    def finden(werte):
        n = schluessel_fn(werte)
        if not n:
            return None
        if n in genau:
            return Treffer(genau[n].id, True)
        for k, b in genau.items():
            if len(n) >= 4 and (
                difflib.SequenceMatcher(None, n, k).ratio() >= 0.85
                or (len(k) >= 4 and (k in n or n in k))
            ):
                return Treffer(b.id, False, "ähnlicher Name")
        return None

    return finden


# --- Ausgabestellen ---------------------------------------------------------------------

STELLE_FELDER = [
    Feld(
        "name",
        "Name",
        ("ausgabestelle", "stelle", "standort", "filiale", "bezeichnung"),
        pflicht=True,
        laenge=100,
    ),
    Feld(
        "strasse",
        "Straße und Hausnummer",
        ("adresse", "anschrift", "str", "hausnummer", "hausnr"),
        mehrfach=True,
        laenge=200,
    ),
    Feld("plz", "PLZ", ("postleitzahl",), laenge=10),
    Feld("ort", "Ort", ("stadt",), laenge=100),
    Feld("telefon", "Telefon", ("tel", "telefonnummer", "festnetz"), typ="telefon", laenge=50),
    Feld("email", "E-Mail", ("mail", "emailadresse"), typ="email", laenge=254),
    Feld(
        "anmerkung",
        "Anmerkung",
        ("bemerkung", "bemerkungen", "hinweis", "notiz", "info"),
        typ="langtext",
    ),
    Feld("aktiv", "Aktiv (ja/nein)", ("aktiv", "status"), typ="janein"),
]


class Ausgabestellen(Ziel):
    kennung = "ausgabestellen"
    titel = "Ausgabestellen"
    recht = "einstellungen.listen"
    beschreibung = "Name, Anschrift, Telefon, E-Mail und Anmerkung je Ausgabestelle."
    aktionen = [
        ("behalten", "behalten"),
        ("inaktiv", "auf inaktiv setzen"),
        ("loeschen", "löschen (Papierkorb)"),
    ]
    zurueck = ("kunden:ausgabestellen", "Ausgabestellen")

    def arten(self):
        return [Art("ausgabestellen", "Ausgabestellen", STELLE_FELDER)]

    def vergleichsfelder(self):
        # Der Name ist der Schlüssel; eine vorhandene Ausgabestelle behält ihren Namen
        return [(f.schluessel, f.bezeichnung) for f in STELLE_FELDER if f.schluessel != "name"]

    def bestand(self, verwalter):
        from django.urls import reverse

        from apps.kunden.models import Ausgabestelle

        return [
            Bestandseintrag(
                id=str(s.pk),
                name=s.name,
                werte={
                    "name": s.name,
                    "strasse": s.strasse,
                    "plz": s.plz,
                    "ort": s.ort,
                    "telefon": s.telefon,
                    "email": s.email.lower(),
                    "anmerkung": s.anmerkung,
                    "aktiv": "ja" if s.aktiv else "nein",
                },
                link=reverse("kunden:ausgabestelle", args=[s.pk]),
            )
            for s in Ausgabestelle.objects.all()
        ]

    def treffer_finder(self, bestand):
        return _name_treffer(bestand, self.schluessel)

    @transaction.atomic
    def anwenden(self, entscheidung, verwalter):
        from apps.core import papierkorb
        from apps.kunden.models import Ausgabestelle

        def setzen(s, werte):
            for k, v in werte.items():
                if k == "aktiv":
                    s.aktiv = v != "nein"
                elif k != "name" or not s.pk:
                    setattr(s, k, v)

        neu = 0
        for werte in entscheidung.anlegen:
            s = Ausgabestelle()
            setzen(s, werte)
            if Ausgabestelle.objects.filter(name__iexact=s.name).exists():
                continue  # gleichnamige gibt es schon (Namen sind eindeutig)
            s.save()
            neu += 1
        for pk, werte in entscheidung.aendern.items():
            s = Ausgabestelle.objects.get(pk=pk)
            setzen(s, werte)
            s.save()
        inaktiv = geloescht = 0
        for pk, aktion in entscheidung.fehlt.items():
            s = Ausgabestelle.objects.filter(pk=pk).first()
            if s is None:
                continue
            if aktion == "loeschen":
                try:
                    with transaction.atomic():
                        papierkorb.loeschen(
                            verwalter, "Ausgabestelle", s.name, s, recht="einstellungen.listen"
                        )
                    geloescht += 1
                    continue
                except ProtectedError:
                    pass  # noch Kundengruppen oder Konten daran: stattdessen inaktiv
            s.aktiv = False
            s.save(update_fields=["aktiv"])
            inaktiv += 1
        return [
            f"{neu} neu angelegt",
            f"{len(entscheidung.aendern)} aktualisiert",
            f"{inaktiv} auf inaktiv gesetzt",
            f"{geloescht} in den Papierkorb gelegt",
        ]


# --- Mitarbeitende ----------------------------------------------------------------------

MA_FELDER = [
    Feld(
        "benutzername", "Benutzername", ("benutzer", "login", "username", "anmeldename"), laenge=150
    ),
    Feld("anrede", "Anrede", ("geschlecht",), laenge=30),
    Feld("vorname", "Vorname", ("rufname",), pflicht=True, laenge=150),
    Feld("nachname", "Nachname", ("name", "familienname", "zuname"), pflicht=True, laenge=150),
    Feld("email", "E-Mail", ("mail", "emailadresse", "email privat"), typ="email", laenge=254),
    Feld("geburtsdatum", "Geburtsdatum", ("geboren", "gebdatum", "geburtstag", "geb"), typ="datum"),
    Feld(
        "strasse",
        "Straße und Hausnummer",
        ("adresse", "anschrift", "str", "hausnummer", "hausnr"),
        mehrfach=True,
        laenge=200,
    ),
    Feld("plz", "PLZ", ("postleitzahl",), laenge=10),
    Feld("ort", "Ort", ("wohnort", "stadt"), laenge=100),
    Feld(
        "telefon",
        "Telefon",
        ("tel", "telefonnummer", "festnetz", "telefonprivat"),
        typ="telefon",
        laenge=50,
    ),
    Feld(
        "handy",
        "Handy",
        ("mobil", "mobiltelefon", "handynummer", "mobilnummer"),
        typ="telefon",
        laenge=50,
    ),
    Feld("notfall_name", "Notfallkontakt: Name", ("notfallkontakt", "notfall"), laenge=150),
    Feld(
        "notfall_telefon",
        "Notfallkontakt: Telefon",
        ("notfallnummer", "notfalltel"),
        typ="telefon",
        laenge=50,
    ),
    Feld("eintritt", "Eintritt", ("eintrittsdatum", "dabeiseit", "seit", "beginn"), typ="datum"),
    Feld("austritt", "Austritt", ("austrittsdatum", "ende"), typ="datum"),
    Feld("fs_klassen", "Führerscheinklassen", ("fuehrerschein", "klassen", "fsklasse"), laenge=100),
    Feld(
        "beschaeftigung",
        "Beschäftigung (ehrenamtlich/fest)",
        ("anstellung", "art", "beschaeftigungsart"),
    ),
    Feld(
        "ausgabestellen",
        "Ausgabestellen",
        ("ausgabestelle", "stelle", "standort", "einsatzort"),
        typ="liste",
    ),
    Feld(
        "rollen",
        "Rollen (nur bei neuen Konten)",
        ("rolle", "funktion", "taetigkeit", "aufgabe"),
        typ="liste",
    ),
    Feld(
        "bemerkung", "Anmerkung", ("anmerkungen", "bemerkungen", "notiz", "hinweis"), typ="langtext"
    ),
]
STAMMDATEN = [
    "anrede",
    "geburtsdatum",
    "strasse",
    "plz",
    "ort",
    "telefon",
    "handy",
    "notfall_name",
    "notfall_telefon",
    "eintritt",
    "austritt",
    "fs_klassen",
    "bemerkung",
]
DATUMSFELDER = {"geburtsdatum", "eintritt", "austritt"}


def _beschaeftigung(text: str) -> str:
    n = normalisieren(text)
    if not n:
        return ""
    return (
        "fest angestellt"
        if any(w in n for w in ("fest", "angestellt", "haupt", "minijob", "teilzeit", "vollzeit"))
        else "ehrenamtlich"
    )


class Mitarbeitende(Ziel):
    kennung = "mitarbeitende"
    titel = "Mitarbeitende"
    recht = "mitarbeitende.verwalten"
    beschreibung = (
        "Konten mit Anschrift und Stammdaten. Neue Konten bekommen kein Passwort; "
        "Zugang später per Einladung oder neuem Passwort."
    )
    aktionen = [("behalten", "behalten"), ("sperren", "sperren")]
    zurueck = ("konten:mitarbeitende", "Mitarbeitende")

    def arten(self):
        return [Art("mitarbeitende", "Mitarbeitende", MA_FELDER)]

    def name(self, werte):
        return f"{werte.get('vorname', '')} {werte.get('nachname', '')}".strip()

    def schluessel(self, werte):
        return (
            werte.get("benutzername", "").lower()
            or werte.get("email", "")
            or normalisieren(self.name(werte)) + werte.get("geburtsdatum", "")
        )

    def vergleichsfelder(self):
        # Rollen ändert der Import bei vorhandenen Konten nie (Rechte nur bewusst vergeben);
        # der Benutzername ist der Schlüssel und bleibt.
        return [
            (f.schluessel, f.bezeichnung)
            for f in MA_FELDER
            if f.schluessel not in ("rollen", "benutzername")
        ]

    def wert(self, f, wert, warnen):
        wert = super().wert(f, wert, warnen)
        if f.schluessel == "beschaeftigung":
            return _beschaeftigung(wert)
        if f.schluessel == "ausgabestellen":
            from apps.kunden.models import Ausgabestelle

            bekannt = {s.lower(): s for s in Ausgabestelle.objects.values_list("name", flat=True)}
            namen = []
            for teil in _liste(wert):
                if teil.lower() in bekannt:
                    namen.append(bekannt[teil.lower()])
                else:
                    warnen(
                        "Unbekannte Ausgabestelle wird nicht zugeordnet (erst unter "
                        "Ausgabestellen anlegen oder importieren)."
                    )
            return ", ".join(sorted(set(namen)))
        if f.schluessel == "rollen":
            return ", ".join(_liste(wert))
        return wert

    def _konten(self):
        from django.contrib.auth import get_user_model

        return (
            get_user_model()
            .objects.filter(stelle__isnull=True)
            .select_related("stammdaten")
            .prefetch_related("ausgabestellen")
        )

    def bestand(self, verwalter):
        from django.urls import reverse

        from apps.konten.models import Stammdaten

        ergebnis = []
        for b in self._konten():
            try:
                sd = b.stammdaten
            except Stammdaten.DoesNotExist:
                sd = Stammdaten(benutzer=b)
            werte = {
                "benutzername": b.username,
                "vorname": b.first_name,
                "nachname": b.last_name,
                "email": b.email.lower(),
                "beschaeftigung": b.get_beschaeftigung_display(),
                "ausgabestellen": ", ".join(sorted(s.name for s in b.ausgabestellen.all())),
            }
            for k in STAMMDATEN:
                v = getattr(sd, k)
                werte[k] = _datum_text(v) if k in DATUMSFELDER else (v or "")
            name = b.get_full_name() or b.username
            ergebnis.append(
                Bestandseintrag(
                    id=str(b.pk),
                    name=name + ("" if b.is_active else " (gesperrt)"),
                    werte=werte,
                    link=reverse("konten:mitarbeiter", args=[b.pk]),
                )
            )
        return ergebnis

    def fehlt_ausnehmen(self, verwalter):
        # Gesperrte und das eigene Konto stehen nicht zur Wahl
        return {str(b.pk) for b in self._konten().filter(is_active=False)} | {str(verwalter.pk)}

    def treffer_finder(self, bestand):
        nach_login = {b.werte["benutzername"].lower(): b for b in bestand}
        nach_mail = {}
        nach_name: dict[str, list] = {}
        for b in bestand:
            if b.werte["email"]:
                nach_mail.setdefault(b.werte["email"], b)
            n = normalisieren(f"{b.werte['vorname']} {b.werte['nachname']}")
            if n:
                nach_name.setdefault(n, []).append(b)

        def finden(werte):
            login = werte.get("benutzername", "").lower()
            if login and login in nach_login:
                return Treffer(nach_login[login].id, True)
            if werte.get("email") and werte["email"] in nach_mail:
                return Treffer(nach_mail[werte["email"]].id, True)
            gleiche = nach_name.get(normalisieren(self.name(werte)), [])
            geb = werte.get("geburtsdatum", "")
            for b in gleiche:
                if geb and b.werte["geburtsdatum"] == geb:
                    return Treffer(b.id, True)
            if gleiche:
                b = gleiche[0]
                if geb and b.werte["geburtsdatum"] and b.werte["geburtsdatum"] != geb:
                    return Treffer(b.id, False, "gleicher Name, anderes Geburtsdatum")
                return Treffer(b.id, False, "gleicher Name")
            return None

        return finden

    def _benutzername(self, werte, vergeben) -> str:
        from django.contrib.auth import get_user_model

        basis = werte.get("benutzername") or ".".join(
            t
            for t in (
                normalisieren(werte.get("vorname", "")),
                normalisieren(werte.get("nachname", "")),
            )
            if t
        )
        basis = (basis or "mitarbeiter")[:140]
        name, zahl = basis, 1
        modell = get_user_model()
        while name.lower() in vergeben or modell.objects.filter(username__iexact=name).exists():
            zahl += 1
            name = f"{basis}{zahl}"
        vergeben.add(name.lower())
        return name

    def _stammdaten(self, benutzer, werte):
        from apps.konten.models import Stammdaten

        sd, _ = Stammdaten.objects.get_or_create(benutzer=benutzer)
        for k in STAMMDATEN:
            if k in werte:
                v = werte[k]
                setattr(sd, k, wertlesen.datum(v) if k in DATUMSFELDER else v)
        sd.save()

    def _konto_felder(self, b, werte):
        for k, attr in (("vorname", "first_name"), ("nachname", "last_name"), ("email", "email")):
            if k in werte:
                setattr(b, attr, werte[k])
        if "beschaeftigung" in werte:
            b.beschaeftigung = (
                "fest" if werte["beschaeftigung"] == "fest angestellt" else ("ehrenamtlich")
            )

    def _stellen(self, b, werte):
        from apps.kunden.models import Ausgabestelle

        if "ausgabestellen" in werte:
            namen = _liste(werte["ausgabestellen"])
            b.ausgabestellen.set(Ausgabestelle.objects.filter(name__in=namen))

    @transaction.atomic
    def anwenden(self, entscheidung, verwalter):
        from django.contrib.auth import get_user_model

        from apps.konten import rollen, verwaltung

        erlaubt = {r.lower(): r for r in verwaltung.vergebbare_rollen(verwalter)}
        hinweise, vergeben = [], set()
        neu = rollen_aus = 0
        for werte in entscheidung.anlegen:
            daten = {"username": self._benutzername(werte, vergeben)}
            b = get_user_model()(**daten)
            self._konto_felder(b, werte)
            namen = [r for r in _liste(werte.get("rollen", "")) if r.lower() in erlaubt]
            rollen_aus += len(_liste(werte.get("rollen", ""))) - len(namen)
            konto, _ = verwaltung.anlegen(
                verwalter,
                {
                    "username": b.username,
                    "first_name": b.first_name,
                    "last_name": b.last_name,
                    "email": b.email,
                    "beschaeftigung": b.beschaeftigung,
                },
                [erlaubt[r.lower()] for r in namen],
                einladung=True,
            )
            self._stammdaten(konto, werte)
            self._stellen(konto, werte)
            neu += 1
        geaendert = uebersprungen = 0
        for pk, werte in entscheidung.aendern.items():
            b = get_user_model().objects.get(pk=pk)
            if not verwaltung.darf_bearbeiten(verwalter, b):
                uebersprungen += 1
                continue
            self._konto_felder(b, werte)
            b.save()
            rollen.rechte_vergessen(b)
            if set(werte) & set(STAMMDATEN):
                self._stammdaten(b, werte)
            self._stellen(b, werte)
            geaendert += 1
        gesperrt = 0
        for pk, aktion in entscheidung.fehlt.items():
            b = get_user_model().objects.filter(pk=pk, is_active=True).first()
            if b is None or aktion != "sperren":
                continue
            try:
                verwaltung.sperren(verwalter, b)
                gesperrt += 1
            except verwaltung.VerwaltungsFehler:
                uebersprungen += 1
        hinweise = [
            f"{neu} neu angelegt (ohne Passwort)",
            f"{geaendert} aktualisiert",
            f"{gesperrt} gesperrt",
        ]
        if uebersprungen:
            hinweise.append(
                f"{uebersprungen} Admin-Konten übersprungen (nur ein Admin darf sie ändern)"
            )
        if rollen_aus:
            hinweise.append(f"{rollen_aus} unbekannte oder nicht erlaubte Rollen nicht vergeben")
        return hinweise


# --- Kundenstamm ------------------------------------------------------------------------

KUNDEN_BEZEICHNUNG = {
    "kundennummer": "Kundennummer",
    "nachname": "Nachname",
    "vorname": "Vorname",
    "anrede": "Anrede",
    "geburtsdatum": "Geburtsdatum",
    "staatsangehoerigkeit": "Staatsangehörigkeit",
    "familienstand": "Familienstand",
    "status": "Status (aktiv, pausiert, gesperrt, beendet)",
    "kundengruppe": "Kundengruppe",
    "ausgabestelle": "Ausgabestelle",
    "kunde_seit": "Kunde seit",
    "ausweis_gueltig_bis": "Ausweis gültig bis",
    "letzter_besuch": "Letzter Besuch",
    "einkommensart": "Einkommensart",
    "strasse": "Straße und Hausnummer",
    "plz": "PLZ",
    "ort": "Ort",
    "telefon": "Telefon",
    "email": "E-Mail",
    "kontostand": "Kontostand",
    "anzahl_erwachsene": "Anzahl Erwachsene",
    "anzahl_kinder": "Anzahl Kinder",
    "eigene_kundennummer": "Eigene Kundennummer",
    "von": "Von",
    "bis": "Bis",
    "begruendung": "Begründung",
    "eingetragen_von": "Eingetragen von",
    "datum": "Datum",
    "text": "Text",
    "verfasst_von": "Verfasst von",
    "kuerzel": "Kürzel",
    "name": "Name",
    "wochentage": "Wochentage",
    "uhrzeit": "Uhrzeit",
    "maximum": "Höchstzahl",
    "aktiv": "Aktiv",
    "beitrag": "Beitrag",
}
KUNDEN_SYNONYME = {
    "kundennummer": (
        "kdnr",
        "kundennr",
        "kunden-nr",
        "nummer",
        "ausweisnummer",
        "ausweisnr",
        "kartennummer",
        "kundenid",
    ),
    "nachname": ("name", "familienname", "zuname"),
    "vorname": ("rufname",),
    "geburtsdatum": ("geboren", "gebdatum", "gebdat", "geburtstag", "geb"),
    "staatsangehoerigkeit": ("nationalitaet", "herkunft", "herkunftsland"),
    "status": ("kundenstatus",),
    "kundengruppe": ("gruppe", "ausgabegruppe", "termin", "abholgruppe"),
    "ausgabestelle": ("stelle", "standort", "filiale", "ausgabeort"),
    "kunde_seit": (
        "seit",
        "aufnahme",
        "aufnahmedatum",
        "angemeldet",
        "anmeldedatum",
        "kundeseit",
        "eintritt",
    ),
    "ausweis_gueltig_bis": (
        "gueltigbis",
        "gueltig",
        "ablauf",
        "ablaufdatum",
        "berechtigtbis",
        "bescheidbis",
        "ausweisbis",
    ),
    "letzter_besuch": ("letzteabholung", "zuletzt", "letzterbesuch"),
    "einkommensart": ("einkommen", "leistung", "leistungsart", "bezug", "nachweis", "berechtigung"),
    "strasse": ("adresse", "anschrift", "str", "hausnummer", "hausnr"),
    "plz": ("postleitzahl",),
    "ort": ("wohnort", "stadt"),
    "telefon": ("tel", "telefonnummer", "handy", "mobil", "festnetz"),
    "email": ("mail", "emailadresse"),
    "kontostand": ("guthaben", "saldo", "konto"),
    "anzahl_erwachsene": ("erwachsene",),
    "anzahl_kinder": ("kinder",),
    "von": ("ab", "beginn", "gesperrtab"),
    "bis": ("ende", "gesperrtbis"),
    "begruendung": ("grund",),
    "text": ("bemerkung", "anmerkung", "notiz", "kommentar"),
    "verfasst_von": ("verfasser", "autor"),
    "kuerzel": ("kurz", "code"),
    "name": ("bezeichnung",),
    "wochentage": ("tage", "tag", "wochentag"),
    "uhrzeit": ("zeit", "um"),
    "maximum": ("max", "plaetze", "hoechstzahl"),
    "beitrag": ("betrag", "bezahlt"),
}
KUNDEN_ARTEN = {
    "haushalte.csv": "Haushalte (mit Hauptperson)",
    "personen.csv": "Angehörige",
    "abholer.csv": "Abholberechtigte",
    "sperren.csv": "Sperren",
    "bemerkungen.csv": "Anmerkungen",
    "kundengruppen.csv": "Kundengruppen",
    "abholungen.csv": "Abholungen",
    "ausnahmen.csv": "Ausnahmen",
}


class Kunden(Ziel):
    kennung = "kunden"
    titel = "Kundenstamm"
    recht = "kunden.importieren"
    beschreibung = (
        "Haushalte, Angehörige, Abholberechtigte, Sperren, Anmerkungen, "
        "Kundengruppen, Abholungen. Geprüft wird wie beim Importformat."
    )
    zurueck = ("kunden:uebersicht", "Kunden")

    def arten(self):
        from apps.kunden.importieren import SPALTEN
        from apps.kunden.models import Zusatzfeld

        zusatz = [
            Feld(f"zusatz_{z.schluessel}", f"Zusatzfeld: {z.bezeichnung}")
            for z in Zusatzfeld.objects.filter(aktiv=True)
        ]
        arten = []
        for datei, titel in KUNDEN_ARTEN.items():
            felder = [
                Feld(
                    s,
                    KUNDEN_BEZEICHNUNG.get(s, s),
                    KUNDEN_SYNONYME.get(s, ()),
                    pflicht=s in SPALTEN[datei]["pflicht"],
                    mehrfach=s == "strasse",
                )
                for s in SPALTEN[datei]["pflicht"] + SPALTEN[datei]["optional"]
            ]
            if datei in ("haushalte.csv", "personen.csv"):
                felder += zusatz
            arten.append(Art(datei, titel, felder))
        return arten

    @staticmethod
    def neutral(art: Art, zeilen: list[dict]) -> bytes:
        """Zeilen ({Feld: Text}) als CSV-Datei im Importformat."""
        spalten = [f.schluessel for f in art.felder if any(f.schluessel in z for z in zeilen)]
        puffer = io.StringIO()
        schreiber = csv.writer(puffer, delimiter=";", lineterminator="\n")
        schreiber.writerow(spalten)
        for z in zeilen:
            schreiber.writerow([z.get(s, "") for s in spalten])
        return puffer.getvalue().encode("utf-8")


ZIELE = {z.kennung: z for z in (Kunden(), Ausgabestellen(), Mitarbeitende())}


def erlaubte(benutzer) -> list[Ziel]:
    from apps.konten import rollen

    return [z for z in ZIELE.values() if rollen.hat_recht(benutzer, z.recht)]

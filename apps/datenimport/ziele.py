"""Was sich importieren lässt (ADR 0078): je Ziel die Felder, die Prüfung der Werte, der
Bestand zum Abgleich und das Übernehmen.

Der Kundenstamm hat eigene Regeln (Importformat, ``apps.kunden.importieren``): Seine Tabellen
werden nach der Zuordnung in das neutrale Format umgeschrieben und dort geprüft.
"""

import csv
import datetime as dt
import io
import re

from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.db import transaction
from django.db.models import ProtectedError

from apps.datenimport.abgleich import Bestandseintrag, Treffer, abgleichen
from apps.datenimport.zuordnung import NAME_VOLL, PLZ_ORT, Art, Feld, normalisieren
from apps.kunden import werte as wertlesen

FEHLER, WARNUNG = "fehler", "warnung"


def _datum_text(d) -> str:
    # Jahr immer vierstellig: strftime("%Y") liefert für Jahre vor 1000 nur drei Stellen
    # (z. B. „962“), was danach nicht mehr als Datum gelesen werden kann.
    return f"{d.day:02d}.{d.month:02d}.{d.year:04d}" if d else ""


def _liste(text: str) -> list[str]:
    return [t.strip() for t in re.split(r"[,;/|\n]", text or "") if t.strip()]


class Ziel:
    kennung = ""
    titel = ""
    recht = ""
    beschreibung = ""
    aktionen: list[tuple[str, str]] = [("behalten", "behalten")]
    zurueck = ("core:start", "Start")  # Seite nach dem Übernehmen (dahinter ggf. Argumente)

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
    Feld("telefon_kunden", "Telefon für Kunden", ("kundentelefon", "telfuerkunden"),
         typ="telefon", laenge=50),
    Feld("fax", "Fax", ("telefax", "faxnummer"), laenge=50),
    Feld("plaetze", "Plätze (Haushalte je Ausgabe)", ("plaetze", "kapazitaet", "maximum")),
    Feld("helfer", "Helfer je Ausgabe", ("helfer", "helferzahl", "anzahlhelfer")),
    Feld("barrierefrei", "Barrierefrei (ja/nein)", ("barrierefreiheit", "rollstuhl"), typ="janein"),
    Feld("wlan", "WLAN (ja/nein)", ("wifi", "internet"), typ="janein"),
    Feld("zeiten", "Ausgabezeiten (z. B. „Di 13:00; Do 14:00“)",
         ("ausgabezeit", "ausgabezeiten", "zeit", "zeiten", "termin")),
    *[
        Feld(f"kontakt{n}_{teil}", f"Ansprechpartner {n}: {text}", (), typ=typ,
             laenge=laenge)
        for n in (1, 2, 3)
        for teil, text, typ, laenge in (("name", "Name", "text", 150),
                                        ("telefon", "Telefon", "telefon", 50),
                                        ("email", "E-Mail", "email", 254))
    ],
]  # fmt: skip
TAGE_KURZ = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]


def _zeiten(text: str) -> list[tuple[int, str]]:
    """„Di 13:00; Do 14.00 Uhr“ → [(1, "13:00"), (3, "14:00")]; Unlesbares fällt weg."""
    ergebnis = []
    for tag, stunde, minute in re.findall(
        r"\b(mo|di|mi|do|fr|sa|so)[a-z]*\.?\s*(\d{1,2})[:.](\d{2})", (text or "").lower()
    ):
        eintrag = (TAGE_KURZ.index(tag.capitalize()), f"{int(stunde):02d}:{minute}")
        if eintrag not in ergebnis and int(stunde) < 24 and int(minute) < 60:
            ergebnis.append(eintrag)
    return ergebnis


def _zeiten_text(zeiten) -> str:
    return "; ".join(f"{TAGE_KURZ[t]} {z}" for t, z in sorted(zeiten))


class Ausgabestellen(Ziel):
    kennung = "ausgabestellen"
    titel = "Ausgabestellen"
    recht = "einstellungen.listen"
    beschreibung = (
        "Name, Anschrift, Telefon, E-Mail, Anmerkung, Plätze, Helfer, Ausstattung, "
        "Ausgabezeiten und bis zu drei Ansprechpartner je Ausgabestelle."
    )
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

    def wert(self, f, wert, warnen):
        if f.schluessel == "zeiten" and wert:
            zeiten = _zeiten(wert)
            if not zeiten:
                warnen("„Ausgabezeiten“ sind nicht lesbar (z. B. „Di 13:00“) und bleiben leer.")
            return _zeiten_text(zeiten)
        if f.schluessel in ("plaetze", "helfer") and wert:
            zahl = re.match(r"\s*(\d+)", wert)
            if not zahl:
                warnen(f"„{f.bezeichnung}“ ist keine Zahl und bleibt leer.")
            return zahl.group(1) if zahl else ""
        return super().wert(f, wert, warnen)

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
                    **self._mehr(s),
                },
                link=reverse("kunden:ausgabestelle", args=[s.pk]),
            )
            for s in Ausgabestelle.objects.prefetch_related("zeiten", "kontakte__benutzer")
        ]

    @staticmethod
    def _mehr(s) -> dict:
        werte = {
            "telefon_kunden": s.telefon_kunden,
            "fax": s.fax,
            "plaetze": str(s.plaetze or ""),
            "helfer": str(s.helfer or ""),
            "barrierefrei": {True: "ja", False: "nein"}.get(s.barrierefrei, ""),
            "wlan": s.wlan,
            "zeiten": _zeiten_text(
                (z.wochentag, f"{z.von:%H:%M}") for z in s.zeiten.all() if z.art == "Ausgabe"
            ),  # fmt: skip
        }
        kontakte = list(s.kontakte.all())
        for n in (1, 2, 3):
            k = kontakte[n - 1] if len(kontakte) >= n else None
            werte[f"kontakt{n}_name"] = k.anzeige_name if k else ""
            werte[f"kontakt{n}_telefon"] = k.telefon if k else ""
            werte[f"kontakt{n}_email"] = k.anzeige_email.lower() if k else ""
        return werte

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
                elif k in ("plaetze", "helfer"):
                    setattr(s, k, int(v) if v else None)
                elif k == "barrierefrei":
                    s.barrierefrei = {"ja": True, "nein": False}.get(v)
                elif k == "zeiten" or k.startswith("kontakt"):
                    continue  # nach dem Speichern, siehe ergaenzen()
                elif k != "name" or not s.pk:
                    setattr(s, k, v)

        def ergaenzen(s, werte):
            """Ausgabezeiten nur hinzufügen (nie löschen); Ansprechpartner 1–3 der Reihe nach."""
            from apps.kunden.models import AusgabestelleKontakt, AusgabestelleZeit

            for tag, zeit in _zeiten(werte.get("zeiten", "")):
                zeit = dt.time.fromisoformat(zeit)
                AusgabestelleZeit.objects.get_or_create(ausgabestelle=s, wochentag=tag, von=zeit,
                                                        art="Ausgabe")  # fmt: skip
            kontakte = list(s.kontakte.all())
            for n in (1, 2, 3):
                teile = {t: werte[f"kontakt{n}_{t}"] for t in ("name", "telefon", "email")
                         if f"kontakt{n}_{t}" in werte}  # fmt: skip
                if not any(teile.values()):
                    continue
                k = kontakte[n - 1] if len(kontakte) >= n else AusgabestelleKontakt(
                    ausgabestelle=s, zustaendigkeit="Ansprechpartner")  # fmt: skip
                if "name" in teile and not k.benutzer_id:
                    k.name = teile["name"]
                for t in ("telefon", "email"):
                    if t in teile:
                        setattr(k, t, teile[t])
                if k.name or k.benutzer_id:
                    k.save()

        neu = 0
        for werte in entscheidung.anlegen:
            s = Ausgabestelle()
            setzen(s, werte)
            if Ausgabestelle.objects.filter(name__iexact=s.name).exists():
                continue  # gleichnamige gibt es schon (Namen sind eindeutig)
            s.save()
            ergaenzen(s, werte)
            neu += 1
        for pk, werte in entscheidung.aendern.items():
            s = Ausgabestelle.objects.get(pk=pk)
            setzen(s, werte)
            s.save()
            ergaenzen(s, werte)
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


# --- Kundengruppen ----------------------------------------------------------------------

GRUPPE_FELDER = [
    Feld("kuerzel", "Kürzel", ("kuerzel", "gruppe", "kennung", "kurz"), laenge=20),
    Feld("name", "Name", ("gruppenname", "bezeichnung", "kundengruppe"), pflicht=True, laenge=100),
    Feld("ausgabestelle", "Ausgabestelle", ("ausgabestellen", "stelle", "standort"), laenge=100),
    Feld("wochentage", "Wochentage", ("wochentag", "tage", "tag")),
    Feld("uhrzeit", "Uhrzeit (z. B. 12:30 oder „Freitag 12:30-13:00“)",
         ("zeit", "beginn", "beschreibung")),
    Feld("maximum", "Maximum Haushalte", ("maximum", "max", "plaetze", "kapazitaet")),
    Feld("farbe", "Farbe", ("farbe", "kennfarbe")),
    Feld("aktiv", "Aktiv (ja/nein)", ("aktiv", "status"), typ="janein"),
]  # fmt: skip


class Kundengruppen(Ziel):
    kennung = "kundengruppen"
    titel = "Kundengruppen"
    recht = "einstellungen.listen"
    beschreibung = ("Kürzel, Name, Ausgabestelle, Wochentage, Uhrzeit, Maximum und Farbe je "
                    "Kundengruppe; die Ausgabestellen müssen schon angelegt sein.")  # fmt: skip
    aktionen = [("behalten", "behalten"), ("inaktiv", "auf inaktiv setzen")]
    zurueck = ("kunden:liste", "Kundengruppen", "kundengruppen")

    def arten(self):
        return [Art("kundengruppen", "Kundengruppen", GRUPPE_FELDER)]

    def name(self, werte):
        return werte.get("name", "")

    def schluessel(self, werte):
        return normalisieren(werte.get("kuerzel") or werte.get("name", ""))

    def vergleichsfelder(self):
        return [(f.schluessel, f.bezeichnung) for f in GRUPPE_FELDER if f.schluessel != "kuerzel"]

    def wert(self, f, wert, warnen):
        from apps.ausgabe.ampel import WOCHENTAGE, wochentage
        from apps.core.auswahl import GRUPPENFARBEN

        if not wert:
            return ""
        if f.schluessel == "wochentage":
            tage = set(wochentage(wert))
            if not tage:
                warnen("„Wochentage“ sind nicht lesbar (z. B. „Mo, Di“) und bleiben leer.")
            return ", ".join(t for t in WOCHENTAGE if t in tage)
        if f.schluessel == "uhrzeit":
            zeit = re.search(r"(\d{1,2})[:.](\d{2})", wert)
            if not zeit or int(zeit.group(1)) > 23 or int(zeit.group(2)) > 59:
                warnen("„Uhrzeit“ ist nicht lesbar und bleibt leer.")
                return ""
            return f"{int(zeit.group(1)):02d}:{zeit.group(2)}"
        if f.schluessel == "maximum":
            zahl = re.match(r"\s*(\d+)", wert)
            if not zahl:
                warnen("„Maximum Haushalte“ ist keine Zahl und bleibt leer.")
            return zahl.group(1) if zahl else ""
        if f.schluessel == "farbe":
            farben = {normalisieren(text): wert for wert, text in GRUPPENFARBEN if wert}
            farben.update({normalisieren(w): w for w, _ in GRUPPENFARBEN if w})
            gefunden = farben.get(normalisieren(wert), "")
            if not gefunden:
                warnen("„Farbe“ gibt es in bintafeln nicht und bleibt leer.")
            return gefunden
        return super().wert(f, wert, warnen)

    def bestand(self, verwalter):
        from django.urls import reverse

        from apps.kunden.models import Kundengruppe

        return [
            Bestandseintrag(
                id=str(g.pk),
                name=g.name,
                werte={
                    "kuerzel": g.kuerzel,
                    "name": g.name,
                    "ausgabestelle": g.ausgabestelle.name if g.ausgabestelle_id else "",
                    "wochentage": g.wochentage,
                    "uhrzeit": f"{g.uhrzeit:%H:%M}" if g.uhrzeit else "",
                    "maximum": str(g.maximum or ""),
                    "farbe": g.farbe,
                    "aktiv": "ja" if g.aktiv else "nein",
                },
                link=reverse("kunden:listeneintrag", args=["kundengruppen", g.pk]),
            )
            for g in Kundengruppe.objects.select_related("ausgabestelle")
        ]

    def treffer_finder(self, bestand):
        nach_kuerzel = {normalisieren(b.werte["kuerzel"]): b for b in bestand if b.werte["kuerzel"]}
        nach_name = _name_treffer(bestand, lambda w: normalisieren(w.get("name", "")))

        def finden(werte):
            k = normalisieren(werte.get("kuerzel", ""))
            if k and k in nach_kuerzel:
                return Treffer(nach_kuerzel[k].id, True)
            return nach_name(werte)

        return finden

    @transaction.atomic
    def anwenden(self, entscheidung, verwalter):
        from apps.kunden.models import Ausgabestelle, Kundengruppe

        stellen = {normalisieren(s.name): s for s in Ausgabestelle.objects.all()}
        unbekannt = set()

        def setzen(g, werte):
            for k, v in werte.items():
                if k == "aktiv":
                    g.aktiv = v != "nein"
                elif k == "maximum":
                    g.maximum = int(v) if v else None
                elif k == "uhrzeit":
                    g.uhrzeit = v or None
                elif k == "ausgabestelle":
                    g.ausgabestelle = stellen.get(normalisieren(v)) if v else None
                    if v and g.ausgabestelle is None:
                        unbekannt.add(v)
                elif k == "kuerzel" and v and Kundengruppe.objects.filter(
                        kuerzel=v).exclude(pk=g.pk).exists():  # fmt: skip
                    continue  # Kürzel sind eindeutig
                else:
                    setattr(g, k, v)

        neu = 0
        for werte in entscheidung.anlegen:
            if Kundengruppe.objects.filter(name__iexact=werte.get("name", "")).exists():
                continue  # Namen sind eindeutig
            g = Kundengruppe()
            setzen(g, werte)
            g.save()
            neu += 1
        for pk, werte in entscheidung.aendern.items():
            g = Kundengruppe.objects.get(pk=pk)
            if "name" in werte and Kundengruppe.objects.filter(
                    name__iexact=werte["name"]).exclude(pk=pk).exists():  # fmt: skip
                werte = {k: v for k, v in werte.items() if k != "name"}
            setzen(g, werte)
            g.save()
        inaktiv = 0
        for pk in entscheidung.fehlt:
            if entscheidung.fehlt[pk] == "inaktiv":
                inaktiv += Kundengruppe.objects.filter(pk=pk, aktiv=True).update(aktiv=False)
        meldungen = [
            f"{neu} neu angelegt",
            f"{len(entscheidung.aendern)} aktualisiert",
            f"{inaktiv} auf inaktiv gesetzt",
        ]
        if unbekannt:
            meldungen.append(f"{len(unbekannt)} Ausgabestelle(n) nicht gefunden – dort ohne "
                             "Ausgabestelle angelegt")  # fmt: skip
        return meldungen


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

    def _adresse_aktualisieren(self, konto, werte):
        """Jedes Konto ist auch eine Person im Adressbuch (ADR 0097). verwaltung.anlegen()
        legt die Adresse schon an, bevor die Stammdaten stehen, sie bliebe also ohne
        Anschrift; darum hier die importierten Angaben nachziehen. Nur Felder aus der Datei
        werden gesetzt, damit ein Lauf von Hand gepflegte Adressdaten nicht leert."""
        from apps.adressen.models import Adresse

        adresse = Adresse.objects.filter(konto=konto).first()
        if adresse is None:
            return
        geaendert = False
        if "vorname" in werte:
            adresse.vorname = (konto.first_name or "")[:100]
            geaendert = True
        if "nachname" in werte:
            adresse.nachname = (konto.last_name or konto.get_username())[:100]
            geaendert = True
        if "email" in werte:
            adresse.email = konto.email or ""
            geaendert = True
        for schluessel, feld in (
            ("anrede", "anrede"),
            ("strasse", "strasse"),
            ("plz", "plz"),
            ("ort", "ort"),
            ("telefon", "telefon"),
            ("handy", "mobil"),
        ):
            if schluessel in werte:
                setattr(adresse, feld, werte[schluessel] or "")
                geaendert = True
        if geaendert:
            adresse.save()

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
            self._adresse_aktualisieren(konto, werte)
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
            self._adresse_aktualisieren(b, werte)
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


# --- Adressbuch und Mitglieder ---------------------------------------------------------

ADRESS_FELDER = [
    Feld("art", "Art (Person oder Organisation)", ("adressart", "typ")),
    Feld(
        "organisation",
        "Organisation",
        ("firma", "verein", "markt", "einrichtung", "institution"),
        laenge=200,
    ),
    Feld("anrede", "Anrede", (), laenge=30),
    Feld("vorname", "Vorname", ("rufname",), laenge=100),
    Feld("nachname", "Nachname", ("name", "familienname", "zuname"), laenge=100),
    Feld(
        "ansprechperson",
        "Ansprechperson",
        ("ansprechpartner", "kontakt", "kontaktperson"),
        laenge=200,
    ),
    Feld(
        "strasse",
        "Straße und Hausnummer",
        ("adresse", "anschrift", "str", "hausnummer", "hausnr"),
        mehrfach=True,
        laenge=200,
    ),
    Feld("plz", "PLZ", ("postleitzahl",), laenge=10),
    Feld("ort", "Ort", ("stadt", "wohnort"), laenge=100),
    Feld("land", "Land", (), laenge=100),
    Feld("telefon", "Telefon", ("tel", "telefonnummer", "festnetz"), typ="telefon", laenge=50),
    Feld("mobil", "Mobil", ("handy", "mobiltelefon", "handynummer"), typ="telefon", laenge=50),
    Feld("email", "E-Mail", ("mail", "emailadresse"), typ="email", laenge=254),
    Feld("webseite", "Webseite", ("homepage", "internet", "url", "web", "www")),
    Feld(
        "kategorien",
        "Kategorien (werden ergänzt)",
        ("kategorie", "gruppe", "gruppen", "verteiler"),
        typ="liste",
    ),
    Feld(
        "notiz",
        "Notiz",
        ("bemerkung", "bemerkungen", "anmerkung", "hinweis", "notizen"),
        typ="langtext",
    ),
    Feld(
        "einwilligung_post",
        "Einwilligung Post seit",
        ("einwilligungpost", "post"),
        typ="einwilligung",
    ),
    Feld(
        "einwilligung_email",
        "Einwilligung E-Mail seit",
        ("einwilligungemail", "newsletter"),
        typ="einwilligung",
    ),
    Feld(
        "veroeffentlichen",
        "Name darf veröffentlicht werden seit",
        ("veroeffentlichung", "nennung"),
        typ="einwilligung",
    ),
]
ADRESS_DATUM = {"einwilligung_post", "einwilligung_email", "veroeffentlichen"}
ADRESS_ARTEN = {
    "person": "Person",
    "privat": "Person",
    "privatperson": "Person",
    "organisation": "Organisation",
    "firma": "Organisation",
    "verein": "Organisation",
    "markt": "Organisation",
    "behoerde": "Organisation",
    "unternehmen": "Organisation",
}


def _adress_name(werte) -> str:
    if werte.get("art") == "Organisation" or (
        werte.get("organisation") and not werte.get("nachname")
    ):
        return werte.get("organisation") or ""
    return f"{werte.get('vorname', '')} {werte.get('nachname', '')}".strip()


def _adress_werte(a) -> dict[str, str]:
    werte = {
        f.schluessel: getattr(a, f.schluessel) or ""
        for f in ADRESS_FELDER
        if f.schluessel not in ADRESS_DATUM | {"kategorien", "art"}
    }
    werte["email"] = werte["email"].lower()
    werte["art"] = "Person" if a.art == "person" else "Organisation"
    werte["kategorien"] = ", ".join(sorted(k.name for k in a.kategorien.all()))
    werte.update({k: _datum_text(getattr(a, k)) for k in ADRESS_DATUM})
    return werte


class _AdressRegeln(Ziel):
    """Gemeinsames für Adressbuch und Mitglieder: Prüfen, Erkennen und Schreiben von Adressen."""

    def wert(self, f, wert, warnen):
        if f.typ == "einwilligung" and wert:
            try:
                if wertlesen.ja_nein(wert):  # „ja“ statt Datum: gilt ab heute
                    from django.utils import timezone

                    return _datum_text(timezone.localdate())
                return ""
            except wertlesen.UngueltigerWert:
                return super().wert(Feld(f.schluessel, f.bezeichnung, typ="datum"), wert, warnen)
        wert = super().wert(f, wert, warnen)
        if f.schluessel == "art" and wert:
            art = ADRESS_ARTEN.get(normalisieren(wert))
            if art is None:
                warnen("Unbekannte Art (Person oder Organisation); wird aus dem Namen bestimmt.")
            return art or ""
        if f.schluessel == "webseite" and wert and "://" not in wert:
            return "https://" + wert
        if f.schluessel == "kategorien":
            return ", ".join(sorted({t[:100] for t in _liste(wert)}))
        return wert

    def bereinigen(self, art, zeilen, tabelle):
        saetze, meldungen = super().bereinigen(art, zeilen, tabelle)
        gueltig = []
        for satz in saetze:
            w = satz["werte"]
            if not w.get("art"):
                w["art"] = (
                    "Organisation" if w.get("organisation") and not w.get("nachname") else "Person"
                )
            fehlt = "nachname" if w["art"] == "Person" else "organisation"
            if not w.get(fehlt):
                meldungen.append(
                    {
                        "stufe": FEHLER,
                        "tabelle": tabelle,
                        "zeile": satz["zeile"],
                        "text": "Weder Nachname noch Organisation; Zeile wird ausgelassen.",
                    }
                )
                continue
            gueltig.append(satz)
        return gueltig, meldungen

    def name(self, werte):
        return _adress_name(werte)

    def schluessel(self, werte):
        return werte.get("email") or normalisieren(self.name(werte)) + werte.get("plz", "")

    def _adress_treffer(self, bestand):
        """Treffer über E-Mail oder Name mit PLZ (sicher), sonst gleicher Name (unsicher)."""
        nach_mail, nach_name_plz, nach_name = {}, {}, {}
        for b in bestand:
            if b.werte.get("email"):
                nach_mail.setdefault(b.werte["email"], b)
            n = normalisieren(_adress_name(b.werte))
            nach_name_plz.setdefault(n + b.werte.get("plz", ""), b)
            nach_name.setdefault(n, b)

        def finden(werte):
            if werte.get("email") and werte["email"] in nach_mail:
                return Treffer(nach_mail[werte["email"]].id, True)
            n = normalisieren(self.name(werte))
            if n and n + werte.get("plz", "") in nach_name_plz:
                return Treffer(nach_name_plz[n + werte.get("plz", "")].id, True)
            if n and n in nach_name:
                return Treffer(nach_name[n].id, False, "gleicher Name, andere Anschrift")
            return None

        return finden

    @staticmethod
    def _adresse_setzen(a, werte, verwalter):
        from django.utils import timezone

        from apps.adressen.models import AdressKategorie

        for k, v in werte.items():
            if k == "art":
                a.art = "person" if v == "Person" else "organisation"
            elif k in ADRESS_DATUM:
                setattr(a, k, wertlesen.datum(v))
            elif k != "kategorien" and k in {f.schluessel for f in ADRESS_FELDER}:
                setattr(a, k, v)
        a.geaendert_am, a.geaendert_von = timezone.now(), str(verwalter)[:150]
        a.save()
        if werte.get("kategorien"):
            vorhanden = {k.name.lower(): k for k in AdressKategorie.objects.all()}
            neue = []
            for name in _liste(werte["kategorien"]):
                k = vorhanden.get(name.lower()) or AdressKategorie.objects.create(name=name[:100])
                vorhanden[name.lower()] = k
                neue.append(k)
            a.kategorien.add(*neue)  # ergänzen, nie wegnehmen

    @staticmethod
    def _adresse_finden(werte):
        """Vorhandene Adresse zu einem neuen Mitglied (E-Mail oder Name und PLZ)."""
        from apps.adressen.models import Adresse

        kandidaten = Adresse.objects.filter(mitglied__isnull=True)
        if werte.get("email"):
            treffer = kandidaten.filter(email__iexact=werte["email"]).first()
            if treffer:
                return treffer
        name = normalisieren(_adress_name(werte))
        for a in kandidaten.filter(plz=werte.get("plz", "")):
            if normalisieren(a.name) == name:
                return a
        return None


class Adressbuch(_AdressRegeln):
    kennung = "adressen"
    titel = "Adressbuch"
    recht = "adressen.importieren"
    beschreibung = "Spender, Märkte, Partner, Behörden … mit Kategorien und Einwilligungen."
    aktionen = [("behalten", "behalten"), ("loeschen", "löschen (Papierkorb)")]
    zurueck = ("adressen:liste", "Adressbuch")

    def arten(self):
        return [Art("adressen", "Adressen", ADRESS_FELDER)]

    def bestand(self, verwalter):
        from django.urls import reverse

        from apps.adressen.models import Adresse

        return [
            Bestandseintrag(
                id=str(a.pk),
                name=a.name,
                werte=_adress_werte(a),
                link=reverse("adressen:adresse", args=[a.pk]),
            )
            for a in Adresse.objects.prefetch_related("kategorien")
        ]

    def treffer_finder(self, bestand):
        return self._adress_treffer(bestand)

    def vergleichsfelder(self):
        return [(f.schluessel, f.bezeichnung) for f in ADRESS_FELDER if f.schluessel != "art"]

    @transaction.atomic
    def anwenden(self, entscheidung, verwalter):
        from apps.adressen.models import Adresse
        from apps.core import papierkorb

        for werte in entscheidung.anlegen:
            self._adresse_setzen(Adresse(), werte, verwalter)
        for pk, werte in entscheidung.aendern.items():
            a = Adresse.objects.filter(pk=pk).first()
            if a:
                self._adresse_setzen(a, werte, verwalter)
        geloescht = geblieben = 0
        for pk, aktion in entscheidung.fehlt.items():
            a = Adresse.objects.filter(pk=pk).first()
            if a is None or aktion != "loeschen":
                continue
            try:
                with transaction.atomic():
                    papierkorb.loeschen(verwalter, "Adresse", a.name, a, recht="adressen.loeschen")
                geloescht += 1
            except ProtectedError:
                geblieben += 1  # Spenden, Bestätigungen oder Mitgliedschaft hängen daran
        hinweise = [
            f"{len(entscheidung.anlegen)} neu angelegt",
            f"{len(entscheidung.aendern)} aktualisiert",
            f"{geloescht} in den Papierkorb gelegt",
        ]
        if geblieben:
            hinweise.append(
                f"{geblieben} behalten, weil Spenden oder eine Mitgliedschaft daran hängen"
            )
        return hinweise


MITGLIED_FELDER = [
    Feld(
        "nummer",
        "Mitgliedsnummer",
        ("mitgliedsnr", "mitgliednr", "mitgliedsnummer", "nr", "nummer"),
        laenge=20,
    ),
    Feld("mitgliedsart", "Art der Mitgliedschaft", ("mitgliedschaft", "mitgliedart", "status")),
    Feld(
        "eintritt", "Eintritt", ("eintrittsdatum", "beitritt", "mitgliedseit", "seit"), typ="datum"
    ),
    Feld("austritt", "Austritt", ("austrittsdatum", "ende", "kuendigung"), typ="datum"),
    Feld("austrittsgrund", "Grund des Austritts", ("austrittsgrund",), laenge=50),
    Feld("jahresbeitrag", "Jahresbeitrag", ("beitrag", "mitgliedsbeitrag", "betrag"), typ="betrag"),
    Feld("zahlweise", "Zahlweise", ("zahlungsweise", "rhythmus", "turnus"), laenge=30),
    Feld("zahlungsart", "Zahlungsart", ("zahlart", "zahlung"), laenge=30),
    Feld("mitglied_notiz", "Notiz zur Mitgliedschaft", ("mitgliedsnotiz",), typ="langtext"),
]
MITGLIED_DATUM = {"eintritt", "austritt"}


class Mitglieder(_AdressRegeln):
    kennung = "mitglieder"
    titel = "Mitglieder"
    recht = "mitglieder.bearbeiten"
    beschreibung = (
        "Mitglieder des Vereins mit Anschrift, Eintritt, Art und Beitrag; die "
        "Anschrift landet im Adressbuch."
    )
    aktionen = [("behalten", "behalten"), ("austritt", "Austritt mit heutigem Datum")]
    zurueck = ("mitglieder:liste", "Mitglieder")

    def arten(self):
        return [Art("mitglieder", "Mitglieder", MITGLIED_FELDER + ADRESS_FELDER)]

    def wert(self, f, wert, warnen):
        if f.typ == "betrag" and wert:
            try:
                betrag = wertlesen.betrag(wert)
            except wertlesen.UngueltigerWert:
                warnen(f"„{f.bezeichnung}“ ist kein Betrag und bleibt leer.")
                return ""
            if betrag is not None and betrag < 0:
                warnen(f"„{f.bezeichnung}“ ist negativ und bleibt leer.")
                return ""
            return f"{betrag:.2f}".replace(".", ",") if betrag is not None else ""
        return super().wert(f, wert, warnen)

    def schluessel(self, werte):
        return werte.get("nummer") or super().schluessel(werte)

    def vergleichsfelder(self):
        return [
            (f.schluessel, f.bezeichnung)
            for f in MITGLIED_FELDER + ADRESS_FELDER
            if f.schluessel not in ("nummer", "art")
        ]

    def _mitglieder(self):
        from apps.mitglieder.models import Mitglied

        return Mitglied.objects.select_related("adresse").prefetch_related("adresse__kategorien")

    def bestand(self, verwalter):
        from django.urls import reverse

        ergebnis = []
        for m in self._mitglieder():
            werte = _adress_werte(m.adresse)
            werte.update(
                {
                    "nummer": m.nummer,
                    "mitgliedsart": m.art,
                    "eintritt": _datum_text(m.eintritt),
                    "austritt": _datum_text(m.austritt),
                    "austrittsgrund": m.austrittsgrund,
                    "jahresbeitrag": f"{m.jahresbeitrag:.2f}".replace(".", ","),
                    "zahlweise": m.zahlweise,
                    "zahlungsart": m.zahlungsart,
                    "mitglied_notiz": m.notiz,
                }
            )
            ergebnis.append(
                Bestandseintrag(
                    id=str(m.pk),
                    name=f"{m.nummer} · {m.adresse.name}",
                    werte=werte,
                    link=reverse("mitglieder:mitglied", args=[m.pk]),
                )
            )
        return ergebnis

    def fehlt_ausnehmen(self, verwalter):
        return {
            str(pk)
            for pk in self._mitglieder().filter(austritt__isnull=False).values_list("pk", flat=True)
        }

    def treffer_finder(self, bestand):
        nach_nummer = {b.werte["nummer"].lower(): b for b in bestand}
        ueber_adresse = self._adress_treffer(bestand)

        def finden(werte):
            if werte.get("nummer") and werte["nummer"].lower() in nach_nummer:
                return Treffer(nach_nummer[werte["nummer"].lower()].id, True)
            t = ueber_adresse(werte)
            if t and t.sicher and werte.get("nummer"):
                # gleiche Person, aber andere Mitgliedsnummer: lieber nachfragen
                return Treffer(t.id, False, "gleiche Anschrift, andere Mitgliedsnummer")
            return t

        return finden

    @staticmethod
    def _mitglied_setzen(m, werte):
        from decimal import Decimal

        for k, attr in (
            ("mitgliedsart", "art"),
            ("austrittsgrund", "austrittsgrund"),
            ("zahlweise", "zahlweise"),
            ("zahlungsart", "zahlungsart"),
            ("mitglied_notiz", "notiz"),
        ):
            if k in werte:
                setattr(m, attr, werte[k])
        for k in MITGLIED_DATUM:
            if k in werte:
                setattr(m, k, wertlesen.datum(werte[k]))
        if werte.get("jahresbeitrag"):
            m.jahresbeitrag = Decimal(werte["jahresbeitrag"].replace(",", "."))

    @transaction.atomic
    def anwenden(self, entscheidung, verwalter):
        from django.utils import timezone

        from apps.adressen.models import Adresse
        from apps.core.auswahl import MITGLIEDSARTEN
        from apps.mitglieder import models as mm

        einstellungen = mm.MitgliederEinstellungen.laden()
        neu = 0
        for werte in entscheidung.anlegen:
            adresse = self._adresse_finden(werte) or Adresse()
            adress_werte = {
                k: v for k, v in werte.items() if k in {f.schluessel for f in ADRESS_FELDER}
            }
            self._adresse_setzen(adresse, adress_werte, verwalter)
            nummer = werte.get("nummer", "")
            if not nummer or mm.Mitglied.objects.filter(nummer=nummer).exists():
                nummer = mm.naechste_nummer()
            m = mm.Mitglied(
                adresse=adresse,
                nummer=nummer,
                art=MITGLIEDSARTEN[0],
                eintritt=timezone.localdate(),
                jahresbeitrag=einstellungen.standard_beitrag,
            )
            self._mitglied_setzen(m, werte)
            m.save()
            mm.nummer_verbraucht(nummer)
            neu += 1
        for pk, werte in entscheidung.aendern.items():
            m = mm.Mitglied.objects.select_related("adresse").filter(pk=pk).first()
            if m is None:
                continue
            adress_werte = {
                k: v for k, v in werte.items() if k in {f.schluessel for f in ADRESS_FELDER}
            }
            if adress_werte:
                self._adresse_setzen(m.adresse, adress_werte, verwalter)
            self._mitglied_setzen(m, werte)
            m.save()
        ausgetreten = 0
        for pk, aktion in entscheidung.fehlt.items():
            if aktion == "austritt":
                ausgetreten += mm.Mitglied.objects.filter(pk=pk, austritt__isnull=True).update(
                    austritt=timezone.localdate()
                )
        return [
            f"{neu} neu angelegt",
            f"{len(entscheidung.aendern)} aktualisiert",
            f"{ausgetreten} als ausgetreten eingetragen",
        ]


# --- Anträge ----------------------------------------------------------------------------

ANTRAG_FELDER = [
    Feld("laufnummer", "Antragsnummer", ("antragsnummer", "antragsnr", "lfdnr", "laufnr")),
    Feld("vorname", "Vorname", ("rufname",), pflicht=True, laenge=100),
    Feld("nachname", "Nachname", ("name", "familienname", "zuname"), pflicht=True, laenge=100),
    Feld("anrede", "Anrede", ("titel",), laenge=30),
    Feld(
        "geburtsdatum",
        "Geburtsdatum",
        ("geboren", "gebdatum", "gebdat", "geburtstag", "geb"),
        typ="datum",
    ),  # fmt: skip
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
        ("tel", "telefonnummer", "handy", "mobil", "festnetz"),
        typ="telefon",
        laenge=50,
    ),  # fmt: skip
    Feld("email", "E-Mail", ("mail", "emailadresse"), typ="email", laenge=254),
    Feld("familienstand", "Familienstand", (), laenge=50),
    Feld(
        "staatsangehoerigkeit",
        "Staatsangehörigkeit",
        ("nationalitaet", "herkunft", "herkunftsland"),
        laenge=100,
    ),  # fmt: skip
    Feld("gdb", "Grad der Behinderung (0–100)", ("behinderung", "gradderbehinderung")),
    Feld("merkzeichen", "Merkzeichen", (), laenge=60),
    Feld("wochentage", "Bevorzugte Wochentage", ("tage", "tag", "wochentag"), laenge=30),
    Feld(
        "ausgabestelle",
        "Bevorzugte Ausgabestelle",
        ("stelle", "standort", "ausgabeort"),
        laenge=100,
    ),  # fmt: skip
    Feld(
        "kundennummer", "Kundennummer", ("kdnr", "kundennr", "nummer", "ausweisnummer"), laenge=20
    ),
    Feld(
        "eingegangen_am",
        "Eingegangen am",
        ("eingang", "eingangsdatum", "datum", "antragsdatum", "anmeldedatum", "aufnahme"),
        typ="datum",
    ),  # fmt: skip
    Feld("art", "Art (Neuanmeldung/Verlängerung)", ("antragsart",)),
    Feld("status", "Status (neu, in Bearbeitung, erledigt, abgelehnt)", ("antragsstatus",)),
    Feld("nachricht", "Nachricht", ("mitteilung",), typ="langtext"),
    Feld("anmerkung", "Anmerkung", ("kommentar", "comment", "bemerkung", "notiz"), typ="langtext"),
    Feld(
        "angehoerige",
        "Angehörige (je Zeile „Vorname TT.MM.JJJJ“)",
        ("angehoerige", "haushalt", "familienmitglieder", "mitglieder", "personen", "kinder"),
        typ="langtext",
    ),
]
# Codes ↔ angezeigte Texte (die Modell-Auswahl ist stabil; Import und Bestand zeigen den Text,
# gespeichert wird der Code).
ANTRAG_ART = {"neu": "Neuanmeldung", "verlaengerung": "Verlängerung"}
ANTRAG_STATUS = {"neu": "neu", "in_bearbeitung": "in Bearbeitung",
                 "erledigt": "erledigt", "abgelehnt": "abgelehnt"}  # fmt: skip
ANTRAG_STATUS_EINGABE = {
    "neu": "neu", "offen": "neu",
    "inbearbeitung": "in Bearbeitung", "bearbeitung": "in Bearbeitung",
    "erledigt": "erledigt", "fertig": "erledigt", "angenommen": "erledigt",
    "abgelehnt": "abgelehnt", "ablehnung": "abgelehnt",
}  # fmt: skip
# Datum in einer Angehörigen-Zeile, auch mit krummen Leerzeichen („02.10. 2008“).
_ANGEHOERIGE_DATUM = re.compile(r"(\d{1,2})\s*\.\s*(\d{1,2})\s*\.\s*(\d{2,4})")


def _angehoerige(text: str) -> list[tuple[str, dt.date | None]]:
    """Angehörige aus einer Zelle lesen: je Zeile „Vorname TT.MM.JJJJ“. Fehlt der Zeilenumbruch
    (aneinandergehängt), wird an den Datumsangaben getrennt. Liefert (Name, Geburtsdatum|None)."""
    text = (text or "").strip()
    if not text:
        return []
    zeilen = [z for z in re.split(r"[\r\n]+", text) if z.strip()]
    if len(zeilen) <= 1:
        teile = re.findall(r"\D*?\d{1,2}\s*\.\s*\d{1,2}\s*\.\s*\d{2,4}", text)
        if len(teile) > 1:
            zeilen = teile
    ergebnis = []
    for z in zeilen:
        m = _ANGEHOERIGE_DATUM.search(z)
        geb, name = None, z
        if m:
            name = (z[: m.start()] + z[m.end() :]).strip()
            try:
                geb = wertlesen.datum(f"{m.group(1)}.{m.group(2)}.{m.group(3)}")
            except wertlesen.UngueltigerWert:
                geb = None
        name = " ".join(name.split())[:100]
        if name:
            ergebnis.append((name, geb))
    return ergebnis


class Antraege(Ziel):
    kennung = "antraege"
    titel = "Anträge"
    recht = "antraege.bearbeiten"
    beschreibung = (
        "Anträge (Neuanmeldungen) mit Antragsteller und Anschrift, ein Antrag je Zeile. "
        "Jede Zeile wird als eigener Antrag übernommen – es wird nichts zusammengeführt und "
        "nichts mit vorhandenen Anträgen abgeglichen. "
        "Angehörige lassen sich aus einer Spalte „Vorname TT.MM.JJJJ je Zeile“ übernehmen; "
        "Einkommen und Nachweise kommen nicht mit (später im Aufnahme-Assistenten). "
        "Verschickt keine Mails."
    )
    zurueck = ("antraege:liste", "Anträge")

    def arten(self):
        return [Art("antraege", "Anträge", ANTRAG_FELDER)]

    def planen(self, saetze, verwalter):
        """Anträge werden unverändert als Liste übernommen: jede Zeile ein neuer Antrag,
        kein Abgleich mit vorhandenen Anträgen und kein Zusammenführen gleicher Namen
        (anders als bei den übrigen Zielen). Die Antragsnummer übernimmt ``anwenden``."""
        from apps.datenimport.abgleich import Plan

        plan = Plan()
        for i, satz in enumerate(saetze):
            plan.neu.append(
                {
                    "i": i,
                    "zeile": satz["zeile"],
                    "name": self.name(satz["werte"]),
                    "werte": satz["werte"],
                }
            )
        return plan

    def name(self, werte):
        return f"{werte.get('vorname', '')} {werte.get('nachname', '')}".strip()

    def schluessel(self, werte):
        return normalisieren(self.name(werte)) + werte.get("geburtsdatum", "")

    def vergleichsfelder(self):
        # Antragsnummer ist die Kennung; Angehörige werden nur beim Neuanlegen übernommen –
        # beide nicht Feld für Feld abgeglichen.
        ohne = {"laufnummer", "angehoerige"}
        return [(f.schluessel, f.bezeichnung) for f in ANTRAG_FELDER if f.schluessel not in ohne]

    def wert(self, f, wert, warnen):
        if f.schluessel == "eingegangen_am" and wert:
            # Datum mit optionaler Uhrzeit, z. B. „29.07.2024 12:36“. Die Uhrzeit bleibt erhalten.
            erstes = wert.split()[0]
            try:
                tag = wertlesen.datum(erstes[:10] if "-" in erstes[:10] else erstes)
            except wertlesen.UngueltigerWert:
                warnen("„Eingegangen am“ ist kein Datum und bleibt leer.")
                return ""
            zeit = re.search(r"\b(\d{1,2})[:.](\d{2})", wert[len(erstes) :])
            if zeit and int(zeit.group(1)) < 24 and int(zeit.group(2)) < 60:
                return f"{_datum_text(tag)} {int(zeit.group(1)):02d}:{zeit.group(2)}"
            return _datum_text(tag)
        if f.schluessel == "laufnummer" and wert:
            ziffern = wert.strip()
            if not ziffern.isdigit() or int(ziffern) < 1:
                warnen("„Antragsnummer“ ist keine positive Zahl; es wird automatisch nummeriert.")
                return ""
            return str(int(ziffern))
        if f.schluessel == "gdb" and wert:
            ziffern = wert.strip()
            if not ziffern.isdigit() or int(ziffern) > 100:
                warnen("„Grad der Behinderung“ ist keine Zahl von 0 bis 100 und bleibt leer.")
                return ""
            return str(int(ziffern))
        if f.schluessel == "art" and wert:
            return "Verlängerung" if normalisieren(wert).startswith("verl") else "Neuanmeldung"
        if f.schluessel == "status" and wert:
            return ANTRAG_STATUS_EINGABE.get(normalisieren(wert), "neu")
        return super().wert(f, wert, warnen)

    def bestand(self, verwalter):
        from django.urls import reverse
        from django.utils import timezone

        from apps.antraege.models import Antrag

        ergebnis = []
        for a in Antrag.objects.filter(papierkorb_am__isnull=True):
            werte = {
                "laufnummer": str(a.laufnummer or ""),
                "anrede": a.anrede, "vorname": a.vorname, "nachname": a.nachname,
                "geburtsdatum": _datum_text(a.geburtsdatum),
                "strasse": a.strasse, "plz": a.plz, "ort": a.ort,
                "telefon": a.telefon, "email": a.email.lower(),
                "familienstand": a.familienstand, "staatsangehoerigkeit": a.staatsangehoerigkeit,
                "gdb": "" if a.gdb is None else str(a.gdb), "merkzeichen": a.merkzeichen,
                "wochentage": a.wochentage, "ausgabestelle": a.ausgabestelle,
                "kundennummer": a.kundennummer,
                "eingegangen_am": _datum_text(timezone.localdate(a.eingegangen_am)),
                "art": ANTRAG_ART.get(a.art, "Neuanmeldung"),
                "status": ANTRAG_STATUS.get(a.status, "neu"),
                "nachricht": a.nachricht,
            }  # fmt: skip
            ergebnis.append(Bestandseintrag(
                id=str(a.pk), name=f"{a.nummer} · {a.name}", werte=werte,
                link=reverse("antraege:antrag", args=[a.pk]),
            ))  # fmt: skip
        return ergebnis

    def treffer_finder(self, bestand):
        nach_nummer = {b.werte["laufnummer"]: b for b in bestand if b.werte["laufnummer"]}
        nach_name: dict[str, list] = {}
        for b in bestand:
            n = normalisieren(f"{b.werte['vorname']} {b.werte['nachname']}")
            if n:
                nach_name.setdefault(n, []).append(b)

        def finden(werte):
            nummer = werte.get("laufnummer", "")
            if nummer and nummer in nach_nummer:
                return Treffer(nach_nummer[nummer].id, True)
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

    @staticmethod
    def _setzen(a, werte):
        from django.utils import timezone

        code = {v: k for k, v in ANTRAG_ART.items()}
        status_code = {v: k for k, v in ANTRAG_STATUS.items()}
        for k in ("anrede", "vorname", "nachname", "strasse", "plz", "ort", "telefon", "email",
                  "familienstand", "staatsangehoerigkeit", "merkzeichen", "wochentage",
                  "ausgabestelle", "kundennummer", "nachricht"):  # fmt: skip
            if k in werte:
                setattr(a, k, werte[k])
        if "geburtsdatum" in werte:
            geb = werte["geburtsdatum"]
            # Eine krumme Angabe bleibt leer, statt den ganzen Import zu sprengen.
            try:
                a.geburtsdatum = wertlesen.datum(geb) if geb else None
            except wertlesen.UngueltigerWert:
                a.geburtsdatum = None
        if "gdb" in werte:
            a.gdb = int(werte["gdb"]) if werte["gdb"] else None
        if "art" in werte:
            a.art = code.get(werte["art"], "neu")
        if werte.get("status"):
            a.status = status_code.get(werte["status"], "neu")
        if werte.get("eingegangen_am"):
            roh = werte["eingegangen_am"]
            try:
                tag = wertlesen.datum(roh.split()[0])
            except wertlesen.UngueltigerWert:
                tag = None
            if tag:
                zeit = re.search(r"(\d{1,2}):(\d{2})", roh)
                uhr = dt.time(int(zeit.group(1)), int(zeit.group(2))) if zeit else dt.time()
                a.eingegangen_am = timezone.make_aware(dt.datetime.combine(tag, uhr))

    @transaction.atomic
    def anwenden(self, entscheidung, verwalter):
        from apps.antraege.models import Antrag, AntragAnmerkung, AntragPerson

        neu = angehoerige = 0
        # Erst die Anträge mit eigener Nummer anlegen, dann die ohne: So zählt die automatische
        # Nummerierung oberhalb der höchsten übernommenen Nummer weiter (naechste_antragsnummer).
        mit_nummer = [w for w in entscheidung.anlegen if w.get("laufnummer", "").isdigit()]
        ohne_nummer = [w for w in entscheidung.anlegen if not w.get("laufnummer", "").isdigit()]
        for werte in mit_nummer + ohne_nummer:
            a = Antrag(sprache="de")
            self._setzen(a, werte)
            nummer = werte.get("laufnummer", "")
            # Nummer aus dem Altprogramm übernehmen, wenn sie frei ist; sonst automatisch vergeben.
            if nummer.isdigit() and not Antrag.objects.filter(laufnummer=int(nummer)).exists():
                a.laufnummer = int(nummer)
            a.save()  # leere laufnummer = automatisch fortlaufend (über der höchsten Nummer)
            neu += 1
            # Angehörige nur beim Neuanlegen (bei vorhandenen Anträgen käme es zu Dubletten).
            for vorname, geb in _angehoerige(werte.get("angehoerige", "")):
                AntragPerson.objects.create(antrag=a, vorname=vorname, geburtsdatum=geb)
                angehoerige += 1
            if werte.get("anmerkung"):
                AntragAnmerkung.objects.create(antrag=a, text=werte["anmerkung"], von="Import")
        for pk, werte in entscheidung.aendern.items():
            a = Antrag.objects.filter(pk=pk).first()
            if a is None:
                continue
            self._setzen(a, werte)
            a.save()
        hinweise = [f"{neu} neu angelegt", f"{len(entscheidung.aendern)} aktualisiert"]
        if angehoerige:
            hinweise.append(f"{angehoerige} Angehörige übernommen")
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
    "betrag": ("summe", "wert", "buchung", "buchungsbetrag"),
    "art": ("buchungsart", "vorgang", "typ"),
    "bar": ("bargeld", "barbetrag"),
    "bemerkung": ("buchungstext", "verwendungszweck", "anmerkung"),
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
    "buchungen.csv": "Kontobuchungen",
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
    def neutral(art: Art, zeilen: list[dict], zugeordnet=()) -> bytes:
        """Zeilen ({Feld: Text}) als CSV-Datei im Importformat. ``zugeordnet``: Felder aus der
        Zuordnung, damit auch eine Datei ohne Datenzeilen ihre Überschriften behält (z. B. eine
        leere Haushalte-Liste für den Vollaustausch)."""
        da = set(zugeordnet)
        if NAME_VOLL in da:
            da |= {"vorname", "nachname"}
        if PLZ_ORT in da:
            da |= {"plz", "ort"}
        spalten = [
            f.schluessel
            for f in art.felder
            if f.schluessel in da or any(f.schluessel in z for z in zeilen)
        ]
        puffer = io.StringIO()
        schreiber = csv.writer(puffer, delimiter=";", lineterminator="\n")
        schreiber.writerow(spalten)
        for z in zeilen:
            schreiber.writerow([z.get(s, "") for s in spalten])
        return puffer.getvalue().encode("utf-8")


ZIELE = {
    z.kennung: z
    for z in (
        Kunden(),
        Ausgabestellen(),
        Kundengruppen(),
        Mitarbeitende(),
        Adressbuch(),
        Mitglieder(),
        Antraege(),
    )  # fmt: skip
}


def erlaubte(benutzer) -> list[Ziel]:
    from apps.konten import rollen

    return [z for z in ZIELE.values() if rollen.hat_recht(benutzer, z.recht)]

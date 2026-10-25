"""Musterdaten für eine Test-Installation: alles erfunden, nichts davon ist echt.

Ersetzt Kundenstamm, Anträge, Adressen, Spenden und Mitglieder vollständig durch Beispiele
und legt Muster-Mitarbeitende (Benutzername ``muster-…``) in allen Rollen an. Unverändert bleiben
die Tafel-Einstellungen (Name, Logo, Anschrift), die Ausgabestellen, das Antragsformular mit
seinen Texten und alle Konten, die nicht mit ``muster-`` beginnen.

Aufruf: ``python manage.py musterdaten --ja`` (vorher sichern: ``./betrieb sichern``).
"""

import datetime as dt
import random
import secrets
from decimal import Decimal

from auditlog.context import disable_auditlog
from django.contrib.auth import get_user_model
from django.contrib.auth.models import Group
from django.db import transaction
from django.utils import timezone

from apps.konten import rollen

PRAEFIX = "muster-"

VORNAMEN_W = ["Anna", "Maria", "Elif", "Fatma", "Olena", "Sabine", "Petra", "Aylin", "Lea",
              "Sofia", "Katarzyna", "Nadia", "Ingrid", "Monika", "Zeynep", "Hanna", "Amira",
              "Jana", "Iryna", "Gisela", "Mina", "Leonie", "Rania", "Doris"]  # fmt: skip
VORNAMEN_M = ["Peter", "Ahmet", "Mehmet", "Jan", "Olek", "Thomas", "Karim", "Lukas", "Andrzej",
              "Hassan", "Klaus", "Mustafa", "Dmytro", "Jürgen", "Samir", "Paul", "Emre",
              "Wolfgang", "Ali", "Tobias", "Yusuf", "Frank", "Bilal", "Dieter"]  # fmt: skip
NACHNAMEN = ["Musterfrau", "Beispiel", "Probe", "Testmann", "Erfunden", "Muster", "Demir",
             "Kowalczyk", "Schmidtke", "Yilmaz", "Petrenko", "Al-Beispiel", "Nowak", "Lindner",
             "Kaya", "Bondarenko", "Hartmann", "Öztürk", "Wagnerowski", "Haddad", "Krüger",
             "Şahin", "Novak", "Brandt", "Rahimi", "Vogelsang", "Celik", "Melnyk"]  # fmt: skip
STRASSEN = ["Musterweg", "Beispielstraße", "Probegasse", "Am Testfeld", "Erfundene Allee",
            "Lindenring", "Birkenweg", "Kastanienplatz", "Ahornstraße", "Hauptstraße"]  # fmt: skip
STAATEN = ["Deutschland"] * 10 + ["Türkei", "Ukraine", "Syrien", "Polen", "Afghanistan",
                                   "Rumänien", "Irak", "Bulgarien", "Eritrea"]  # fmt: skip
EINKOMMENSARTEN = ["Bürgergeld", "Grundsicherung im Alter", "Rente", "Asylbewerberleistungen",
                   "Wohngeld", "Kinderzuschlag", "BAföG / Ausbildung"]  # fmt: skip
NOTIZEN = ["Bescheid nachgereicht, gültig bis Jahresende.", "Bringt nächstes Mal den neuen "
           "Rentenbescheid mit.", "Hat nach Babynahrung gefragt.", "Neue Telefonnummer "
           "mitgeteilt.", "Ausweis beschädigt, neuer gedruckt.", "Kommt ab nächster Woche "
           "dienstags."]  # fmt: skip
ANMERKUNGEN = ["Spricht wenig Deutsch, Tochter übersetzt.", "Rollstuhl, Zugang über Rampe.",
               "Bitte auf Unverträglichkeit achten.",
               "Hat sich über Wartezeit beschwert."]  # fmt: skip
ORGANISATIONEN = [
    ("Bäckerei Probe", "Märkte und Lieferanten"), ("Supermarkt Beispielkauf", "Märkte und "
     "Lieferanten"), ("Gemüsehof Erfunden", "Märkte und Lieferanten"), ("Discounter Muster",
     "Märkte und Lieferanten"), ("Ev. Kirchengemeinde Musterstadt", "Partner"),
    ("Caritas-Beispielverband", "Partner"), ("Lokalzeitung Musterblatt", "Presse"),
    ("Sozialamt Musterstadt", "Behörden"), ("Jobcenter Musterkreis", "Behörden"),
    ("Rotary Club Probestadt", "Spender"), ("Autohaus Testmann GmbH", "Spender"),
    ("Sparkasse Musterkreis", "Spender"), ("Stiftung Erfundenes Gutes", "Spender"),
]  # fmt: skip

# Muster-Mitarbeitende: Benutzername (ohne Präfix), Vorname, Nachname, Rollen, fest, Besonderes
KONTEN = [
    ("admin", "Ada", "Admin", [rollen.ADMIN], False, ""),
    ("buero", "Berta", "Büro", [rollen.BUERO], False, ""),
    ("buero-personal", "Bernhard", "Büro-Personal", [rollen.BUERO, rollen.PERSONAL], True, ""),
    ("buero-ausgabe", "Birgit", "Büro-Ausgabe", [rollen.BUERO, rollen.AUSGABE], False, ""),
    ("ausgabe", "Anton", "Ausgabe", [rollen.AUSGABE], False, ""),
    ("ausgabe-stelle", "Aylin", "Ausgabestelle", [rollen.AUSGABE], False, "eine_stelle"),
    ("kiosk", "Kurt", "Kiosk", [rollen.KIOSK], False, ""),
    ("fahrer", "Fritz", "Fahrer", [rollen.FAHRER], True, ""),
    ("beifahrer", "Bea", "Beifahrer", [rollen.BEIFAHRER], False, ""),
    ("fahrer-ausgabe", "Frieda", "Fahrer-Ausgabe", [rollen.FAHRER, rollen.AUSGABE], True, ""),
    ("personal", "Paula", "Personal", [rollen.PERSONAL], True, ""),
    ("gesperrt", "Gustav", "Gesperrt", [rollen.AUSGABE], False, "gesperrt"),
]  # fmt: skip


class Erzeuger:
    def __init__(self, heute: dt.date, passwort: str, haushalte: int = 150, seed: int = 4711):
        self.heute, self.passwort, self.anzahl = heute, passwort, haushalte
        self.r = random.Random(seed)  # noqa: S311 - Musterdaten, keine Sicherheit
        self.zaehler = {}

    # --- Hilfen ---

    def name(self, weiblich=None):
        weiblich = self.r.random() < 0.55 if weiblich is None else weiblich
        vorname = self.r.choice(VORNAMEN_W if weiblich else VORNAMEN_M)
        return ("Frau" if weiblich else "Herr"), vorname, self.r.choice(NACHNAMEN)

    def anschrift(self):
        plz = f"{self.r.randint(10, 99)}{self.r.randint(100, 999)}"
        return f"{self.r.choice(STRASSEN)} {self.r.randint(1, 120)}", plz, "Musterstadt"

    def telefon(self):
        return f"0{self.r.randint(150, 179)} {self.r.randint(1000000, 9999999)}"

    def geburt(self, von_jahren, bis_jahren):
        tage = self.r.randint(von_jahren * 365, bis_jahren * 365)
        return self.heute - dt.timedelta(days=tage)

    def zaehlen(self, was, n=1):
        self.zaehler[was] = self.zaehler.get(was, 0) + n

    # --- Ablauf ---

    def ausfuehren(self) -> dict:
        with transaction.atomic(), disable_auditlog():
            self.leeren()
            self.konten()
            self.kunden()
            self.antraege()
            self.adressen_spenden_mitglieder()
        return self.zaehler

    def leeren(self):
        from apps.adressen.models import Adresse
        from apps.antraege.models import Antrag
        from apps.antraege.models import loeschen as antrag_loeschen
        from apps.ausgabe.models import Buchung, Korrekturwunsch, Sonderaktion, Teilnahme
        from apps.kunden.models import (
            Haushalt,
            HaushaltDokument,
            HaushaltEreignis,
            ImportLauf,
            Notiz,
            Zugriff,
        )
        from apps.mitglieder.models import Mitglied
        from apps.serienbriefe.models import Versand
        from apps.spenden.models import Spende, Zuwendungsbestaetigung

        for d in HaushaltDokument.objects.all():
            d.loeschen()
        for a in Antrag.objects.all():
            antrag_loeschen(a)
        for modell in (Korrekturwunsch, Teilnahme, Buchung, Notiz, HaushaltEreignis, Zugriff,
                       ImportLauf, Haushalt, Versand, Spende, Zuwendungsbestaetigung, Mitglied,
                       Adresse):  # fmt: skip
            modell.objects.all().delete()
        Sonderaktion.objects.filter(bezeichnung__endswith="(Muster)").delete()
        get_user_model().objects.filter(username__startswith=PRAEFIX).delete()

    def konten(self):
        from apps.konten.models import Stammdaten
        from apps.kunden.models import Ausgabestelle
        from apps.personal.models import Abwesenheit, Arbeitsvertrag, Zeitbuchung

        stellen = list(Ausgabestelle.objects.filter(aktiv=True).order_by("name"))
        zone = timezone.get_current_timezone()
        self.konten_liste = []
        for kurz, vorname, nachname, namen, fest, besonderes in KONTEN:
            b = get_user_model().objects.create_user(
                username=PRAEFIX + kurz, password=self.passwort, first_name=vorname,
                last_name=nachname, email=f"{PRAEFIX}{kurz}@example.org",
            )  # fmt: skip
            if fest:
                b.beschaeftigung = b.Beschaeftigung.FEST
            if besonderes == "gesperrt":
                b.is_active, b.gesperrt_am, b.gesperrt_von = False, timezone.now(), "musterdaten"
            b.save()
            b.groups.set(Group.objects.filter(name__in=namen))
            if besonderes == "eine_stelle" and stellen:
                b.ausgabestellen.set(stellen[:1])
            strasse, plz, ort = self.anschrift()
            Stammdaten.objects.create(
                benutzer=b, anrede="Frau" if vorname[-1] == "a" else "Herr",
                geburtsdatum=self.geburt(19, 75), strasse=strasse, plz=plz, ort=ort,
                telefon=self.telefon(), handy=self.telefon(), notfall_name="Erika Beispiel",
                notfall_telefon=self.telefon(), eintritt=self.geburt(1, 8),
                fs_klassen="B, C1" if rollen.FAHRER in namen else "",
                fs_gueltig_bis=self.heute + dt.timedelta(days=900) if rollen.FAHRER in namen
                else None,
                ifsg_erstbelehrung_am=self.geburt(1, 6),
                ifsg_belehrung_am=self.heute - dt.timedelta(days=self.r.randint(30, 700)),
            )  # fmt: skip
            if fest:
                Arbeitsvertrag.objects.create(
                    benutzer=b, beginn=self.heute.replace(month=1, day=1),
                    taetigkeit="Fahrdienst" if rollen.FAHRER in namen else "Verwaltung",
                    wochenstunden=Decimal("30"), urlaubstage=Decimal("30"),
                    stundenlohn=Decimal("14.50"),
                )  # fmt: skip
                for tage in range(1, 15):
                    tag = self.heute - dt.timedelta(days=tage)
                    if tag.weekday() < 5:
                        Zeitbuchung.objects.create(
                            benutzer=b, beginn=dt.datetime.combine(tag, dt.time(8, 0), zone),
                            ende=dt.datetime.combine(tag, dt.time(14, 30), zone),
                        )  # fmt: skip
                start = self.heute + dt.timedelta(days=self.r.randint(10, 60))
                Abwesenheit.objects.create(
                    benutzer=b, art=Abwesenheit.Art.URLAUB, von=start,
                    bis=start + dt.timedelta(days=4), tage=Decimal("5"),
                )  # fmt: skip
            self.konten_liste.append(b)
            self.zaehlen("Mitarbeitende")

    def kunden(self):
        from apps.ausgabe import konto
        from apps.ausgabe.models import AusgabeEinstellungen, Sonderaktion, Teilnahme
        from apps.kunden.models import (
            Abholer,
            Abholung,
            Ausgabestelle,
            Ausnahme,
            Bemerkung,
            Einkommensart,
            Haushalt,
            Kundengruppe,
            Notiz,
            Person,
            Sperre,
        )

        arten = [Einkommensart.objects.get_or_create(bezeichnung=n)[0] for n in EINKOMMENSARTEN]
        gruppen = list(Kundengruppe.objects.filter(aktiv=True))
        if len(gruppen) < 2:  # ohne Gruppen ist der Einlass kaum zu testen
            stelle = Ausgabestelle.objects.order_by("name").first()
            for name, tag, zeit in (("Muster Di 14:00", "Di", "14:00"),
                                    ("Muster Do 10:00", "Do", "10:00")):  # fmt: skip
                g, _ = Kundengruppe.objects.get_or_create(
                    name=name, defaults={"ausgabestelle": stelle, "wochentage": tag,
                                         "uhrzeit": dt.time.fromisoformat(zeit), "maximum": 120},
                )  # fmt: skip
                gruppen.append(g)
        einstellungen = AusgabeEinstellungen.laden()
        mitarbeitende = [str(b) for b in self.konten_liste[:6]]
        for i in range(self.anzahl):
            gruppe = self.r.choice(gruppen)
            strasse, plz, ort = self.anschrift()
            status = self.r.choices(["aktiv", "pausiert", "gesperrt", "beendet"],
                                    [85, 6, 4, 5])[0]  # fmt: skip
            h = Haushalt.objects.create(
                kundennummer=str(10001 + i), status=status, kundengruppe=gruppe,
                kunde_seit=self.geburt(0, 6), einkommensart=self.r.choice(arten),
                ausweis_gueltig_bis=self.heute + dt.timedelta(days=self.r.randint(-40, 400)),
                strasse=strasse, plz=plz, ort=ort, telefon=self.telefon(),
                email=f"kunde{10001 + i}@example.org" if self.r.random() < 0.3 else "",
                kontostand=Decimal("0"),
            )  # fmt: skip
            anrede, vorname, nachname = self.name()
            Person.objects.create(
                haushalt=h, ist_hauptperson=True, anrede=anrede, vorname=vorname,
                nachname=nachname, geburtsdatum=self.geburt(20, 85),
                staatsangehoerigkeit=self.r.choice(STAATEN),
                familienstand=self.r.choice(["ledig", "verheiratet", "geschieden", "verwitwet"]),
            )  # fmt: skip
            for _ in range(self.r.choices([0, 1, 2, 3, 4, 5], [25, 25, 20, 15, 10, 5])[0]):
                _, vn, _ = self.name()
                Person.objects.create(haushalt=h, vorname=vn, nachname=nachname,
                                      geburtsdatum=self.geburt(0, 60),
                                      staatsangehoerigkeit=self.r.choice(STAATEN))  # fmt: skip
            if self.r.random() < 0.15:
                _, vn, nn = self.name()
                Abholer.objects.create(haushalt=h, vorname=vn, nachname=nn,
                                       geburtsdatum=self.geburt(25, 70))  # fmt: skip
            if status == "gesperrt" or self.r.random() < 0.03:
                Sperre.objects.create(
                    haushalt=h, von=self.heute - dt.timedelta(days=20),
                    bis=self.heute + dt.timedelta(days=30),
                    begruendung="Ausweis weitergegeben (Muster)",
                    eingetragen_von=self.r.choice(mitarbeitende),
                )  # fmt: skip
            if self.r.random() < 0.05:
                Ausnahme.objects.create(haushalt=h, datum=self.heute,
                                        begruendung="Termin verpasst wegen Arzttermin",
                                        eingetragen_von=self.r.choice(mitarbeitende))  # fmt: skip
            if self.r.random() < 0.2:
                Bemerkung.objects.create(haushalt=h, datum=self.geburt(0, 1),
                                         text=self.r.choice(ANMERKUNGEN),
                                         verfasst_von=self.r.choice(mitarbeitende))  # fmt: skip
            if self.r.random() < 0.3:
                Notiz.objects.create(kundennummer=h.kundennummer, text=self.r.choice(NOTIZEN),
                                     verfasst_von=self.r.choice(mitarbeitende))  # fmt: skip
            if status in ("aktiv", "pausiert"):
                self.abholungen(h, gruppe, einstellungen, mitarbeitende, konto, Abholung)
            self.zaehlen("Haushalte")
        self.zaehlen("Personen", Person.objects.count())
        self.zaehlen("Abholungen", Abholung.objects.count())
        aktion, _ = Sonderaktion.objects.get_or_create(
            bezeichnung="Weihnachtsgutschein (Muster)",
            defaults={"von": self.heute - dt.timedelta(days=10),
                      "bis": self.heute + dt.timedelta(days=30)},
        )  # fmt: skip
        for h in Haushalt.objects.filter(status="aktiv")[:25]:
            Teilnahme.objects.create(aktion=aktion, kundennummer=h.kundennummer,
                                     eingetragen_von=self.r.choice(mitarbeitende))  # fmt: skip

    def abholungen(self, h, gruppe, einstellungen, mitarbeitende, konto, Abholung):
        """Wöchentliche Abholungen der letzten Monate am Termin der Kundengruppe."""
        from apps.ausgabe.ampel import WOCHENTAGE

        tage = [t.strip() for t in (gruppe.wochentage or "").split(",") if t.strip()]
        wochentag = WOCHENTAGE.index(tage[0]) if tage else self.r.randint(0, 4)
        tag = self.heute - dt.timedelta(days=(self.heute.weekday() - wochentag) % 7 + 7)
        beginn = max(h.kunde_seit or tag, self.heute - dt.timedelta(days=180))
        beitrag = Decimal("1.50")
        while tag >= beginn:
            if self.r.random() < 0.75:
                uhr = dt.time(self.r.randint(9, 15), self.r.choice([0, 10, 20, 30, 40, 50]))
                a = Abholung.objects.create(
                    haushalt=h, datum=tag, uhrzeit=uhr, beitrag=beitrag,
                    ausgabestelle=gruppe.ausgabestelle,
                    eingetragen_von=self.r.choice(mitarbeitende),
                )  # fmt: skip
                bar = beitrag if self.r.random() < 0.9 else Decimal("5.00")
                einstellungen.anschreiben_erlaubt = True  # nur im Speicher, für die Muster
                konto.abholung_buchen(a, beitrag, bar, einstellungen, gruppe.ausgabestelle,
                                      a.eingetragen_von)  # fmt: skip
            tag -= dt.timedelta(days=7)
        letzte = h.abholungen.order_by("-datum").first()
        if letzte:
            type(h).objects.filter(pk=h.pk).update(letzter_besuch=letzte.datum)

    def antraege(self):
        from apps.antraege.models import Antrag, AntragAnmerkung, AntragPerson

        jetzt = timezone.now()
        for i in range(18):
            anrede, vorname, nachname = self.name()
            strasse, plz, ort = self.anschrift()
            status = self.r.choices(["neu", "in_bearbeitung", "erledigt", "abgelehnt"],
                                    [8, 5, 3, 2])[0]  # fmt: skip
            a = Antrag.objects.create(
                eingegangen_am=jetzt - dt.timedelta(days=self.r.randint(0, 40),
                                                    hours=self.r.randint(0, 20)),
                art=self.r.choice(["neu", "neu", "verlaengerung"]), status=status,
                anrede=anrede, vorname=vorname, nachname=nachname,
                geburtsdatum=self.geburt(20, 80), strasse=strasse, plz=plz, ort=ort,
                telefon=self.telefon(), email=f"antrag{i}@example.org",
                staatsangehoerigkeit=self.r.choice(STAATEN), wochentage="Di, Do",
                nachricht="Wir sind neu in Musterstadt." if i % 4 == 0 else "",
            )  # fmt: skip
            for _ in range(self.r.randint(0, 3)):
                _, vn, _ = self.name()
                AntragPerson.objects.create(
                    antrag=a, vorname=vn, nachname=nachname, geburtsdatum=self.geburt(1, 50),
                    staatsangehoerigkeit=self.r.choice(STAATEN),
                )  # fmt: skip
            if status != "neu":
                AntragAnmerkung.objects.create(antrag=a, text="Telefonisch Termin vereinbart.",
                                               von=str(self.konten_liste[1]))  # fmt: skip
            self.zaehlen("Anträge")

    def adressen_spenden_mitglieder(self):
        from apps.adressen.models import Adresse, AdressKategorie
        from apps.mitglieder.models import Mitglied, MitgliederEinstellungen
        from apps.spenden.models import Spende

        kategorien = {}
        for name in ("Spender", "Märkte und Lieferanten", "Partner", "Presse", "Behörden",
                     "Mitglieder"):  # fmt: skip
            kategorien[name], _ = AdressKategorie.objects.get_or_create(name=name)
        adressen = []
        for organisation, kategorie in ORGANISATIONEN:
            strasse, plz, ort = self.anschrift()
            a = Adresse.objects.create(
                art=Adresse.Art.ORGANISATION, organisation=organisation,
                ansprechperson=" ".join(self.name()[1:]), strasse=strasse, plz=plz, ort=ort,
                telefon=self.telefon(), email=f"kontakt{len(adressen)}@example.org",
                einwilligung_post=self.geburt(0, 3),
            )  # fmt: skip
            a.kategorien.add(kategorien[kategorie])
            adressen.append(a)
        personen = []
        for i in range(30):
            anrede, vorname, nachname = self.name()
            strasse, plz, ort = self.anschrift()
            a = Adresse.objects.create(
                art=Adresse.Art.PERSON, anrede=anrede, vorname=vorname, nachname=nachname,
                strasse=strasse, plz=plz, ort=ort, email=f"person{i}@example.org",
                einwilligung_post=self.geburt(0, 3),
                einwilligung_email=self.geburt(0, 2) if i % 2 else None,
            )  # fmt: skip
            a.kategorien.add(kategorien["Spender" if i < 18 else "Mitglieder"])
            personen.append(a)
        self.zaehlen("Adressen", len(adressen) + len(personen))
        spender = adressen[-4:] + personen[:18]
        for _ in range(90):
            Spende.objects.create(
                adresse=self.r.choice(spender), datum=self.geburt(0, 2),
                betrag=Decimal(self.r.choice([10, 20, 25, 50, 50, 100, 150, 250, 500])),
                zweck=self.r.choice(["", "Weihnachten", "Kinderaktion", "Fahrzeug",
                                     "Allgemein"]),
                zahlungsweg=self.r.choice(["Überweisung", "Bar", "Online (z. B. PayPal)"]),
            )  # fmt: skip
        for _ in range(25):
            Spende.objects.create(
                adresse=self.r.choice(adressen[:4]), datum=self.geburt(0, 1),
                art=Spende.Art.SACH, betrag=Decimal(self.r.choice([0, 80, 150, 300])) or None,
                beschreibung=self.r.choice(["Brot und Brötchen vom Vortag", "Obst und Gemüse",
                                            "Molkereiprodukte", "Konserven"]),
                menge=Decimal(self.r.randint(2, 30)),
                einheit=self.r.choice(["Kisten", "kg"]),
                herkunft=Spende.Herkunft.BETRIEB,
            )  # fmt: skip
        self.zaehlen("Spenden", 115)
        e = MitgliederEinstellungen.laden()
        for i, a in enumerate(personen[10:] + adressen[4:6]):
            Mitglied.objects.create(
                adresse=a, nummer=str(i + 1),
                art=self.r.choice(["Ordentliches Mitglied", "Aktives Mitglied",
                                   "Fördermitglied"]) if a.art == Adresse.Art.PERSON
                else "Juristische Person",
                eintritt=self.geburt(0, 10), jahresbeitrag=Decimal("24") if e.beitraege
                else Decimal("0"),
            )  # fmt: skip
            self.zaehlen("Mitglieder")
        e.naechste_nummer = Mitglied.objects.count() + 1
        e.save()


def erzeugen(heute=None, passwort=None, haushalte=150) -> tuple[dict, str]:
    passwort = passwort or secrets.token_urlsafe(9)
    zaehler = Erzeuger(heute or timezone.localdate(), passwort, haushalte).ausfuehren()
    return zaehler, passwort

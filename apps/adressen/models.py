"""Adressbuch (Modul 5, ADR 0044): Spender, Märkte, Partner, Presse, Behörden …

Grundlage für Spenden, Mitglieder und Serienbriefe. Kundendaten gehören nicht hierher; die
bleiben im Kundenstamm.
"""

from auditlog.registry import auditlog
from django.core.exceptions import ValidationError
from django.db import models, transaction

from apps.core import zeichen

# Adressnummern beginnen hier (ADR 0133): Mitglieder haben ihre Mitgliedsnummer (1, 2, 3 …), alle
# anderen Adressen eine Nummer aus diesem eigenen Bereich – wie in Vereinsprogrammen üblich.
ADRESSNUMMER_AB = 2000


class AdressEinstellungen(models.Model):
    EINZIGE_ID = 1
    naechste_nummer = models.PositiveIntegerField(
        "Nächste Adressnummer", default=ADRESSNUMMER_AB,
        help_text="Für Spender und alle anderen Adressen ohne Mitgliedschaft. Mitglieder haben "
        "ihre Mitgliedsnummer. Wählen Sie die Zahl so, dass Mitgliedsnummern sie nie erreichen.",
    )  # fmt: skip

    class Meta:
        verbose_name = "Einstellungen für Adressnummern"
        verbose_name_plural = "Einstellungen für Adressnummern"

    def __str__(self):
        return "Einstellungen für Adressnummern"

    @classmethod
    def laden(cls):
        einstellungen, _ = cls.objects.get_or_create(pk=cls.EINZIGE_ID)
        return einstellungen


def naechste_adressnummer() -> int:
    """Nächste freie Adressnummer (Zeile gesperrt, damit nie doppelt). Übersprungen werden
    vergebene Adressnummern und gleich lautende Mitgliedsnummern, damit eine Nummer im Adressbuch
    immer nur eine Person meint (ADR 0133)."""
    from apps.mitglieder.models import Mitglied

    with transaction.atomic():
        e = AdressEinstellungen.laden()
        e = AdressEinstellungen.objects.select_for_update().get(pk=e.pk)
        nummer = e.naechste_nummer
        while (Adresse.objects.filter(nummer=nummer).exists()
               or Mitglied.objects.filter(nummer=str(nummer)).exists()):  # fmt: skip
            nummer += 1
        e.naechste_nummer = nummer + 1
        e.save(update_fields=["naechste_nummer"])
        return nummer


class AdressKategorie(models.Model):
    name = models.CharField("Name", max_length=100, unique=True)
    aktiv = models.BooleanField("Aktiv", default=True)
    reihenfolge = models.PositiveSmallIntegerField("Reihenfolge", default=0)

    class Meta:
        verbose_name = "Adresskategorie"
        verbose_name_plural = "Adresskategorien"
        ordering = ["reihenfolge", "name"]

    def __str__(self):
        return self.name


def emails_ordnen(text: str, haupt: str = "") -> list[str]:
    """Zerlegt „Weitere E-Mail-Adressen“ (Komma, Semikolon, Leerraum oder Zeilenwechsel) in eine
    geprüfte Liste ohne Doppelte und ohne die Haupt-E-Mail. Ungültiges: ``ValidationError``."""
    from django.core.validators import validate_email

    gesehen, liste = {(haupt or "").strip().lower()}, []
    for teil in (text or "").replace(";", ",").replace("\n", ",").replace(" ", ",").split(","):
        teil = teil.strip()
        if not teil or teil.lower() in gesehen:
            continue
        try:
            validate_email(teil)
        except ValidationError:
            raise ValidationError(f"„{teil}“ ist keine gültige E-Mail-Adresse.") from None
        gesehen.add(teil.lower())
        liste.append(teil)
    return liste


def nach_kategorie(queryset, wert, pfad="adresse__kategorien"):
    """Filter „Kategorie“ für Listen, deren Zeilen an einer Adresse hängen (Team, Mitglieder,
    Spenden): nur Zeilen, deren Adresse die Kategorie trägt. Liefert die gefilterte Abfrage und
    den geprüften Wert (leer = alle)."""
    wert = wert if (wert or "").isdigit() else ""
    if wert:
        # eine Kategorie hängt höchstens einmal an einer Adresse – keine doppelten Zeilen
        queryset = queryset.filter(**{f"{pfad}__pk": wert})
    return queryset, wert


SPENDER = "Spender"  # Kategorie aus Migration 0002, wird bei Spenden automatisch gesetzt


def als_spender_markieren(adressen) -> None:
    """Gibt den Adressen die Kategorie „Spender“ (ADR 0132). Nur hinzufügen, nie entfernen: Wer
    Mitglied oder Helfer ist, bleibt es. Hat die Tafel die Kategorie abgeschaltet, passiert nichts;
    fehlt sie, wird sie angelegt."""
    kategorie, _ = AdressKategorie.objects.get_or_create(name=SPENDER)
    if kategorie.aktiv:
        kategorie.adressen.add(*adressen)


class Adresse(models.Model):
    class Art(models.TextChoices):
        ORGANISATION = "organisation", "Organisation (Markt, Firma, Verein, Behörde …)"
        PERSON = "person", "Person"

    art = models.CharField("Art", max_length=15, choices=Art.choices, default=Art.ORGANISATION)
    organisation = models.CharField("Organisation", max_length=200, blank=True)
    anrede = models.CharField("Anrede", max_length=30, blank=True)
    vorname = models.CharField("Vorname", max_length=100, blank=True)
    nachname = models.CharField("Nachname", max_length=100, blank=True)
    geburtsdatum = models.DateField(
        "Geburtsdatum", null=True, blank=True,
        help_text="Nur bei Personen, z. B. für Geburtstagslisten.",
    )  # fmt: skip
    ansprechperson = models.CharField(
        "Ansprechperson", max_length=200, blank=True,
        help_text="Bei Organisationen, z. B. „Frau Muster, Filialleitung“.",
    )  # fmt: skip
    strasse = models.CharField("Straße und Hausnummer", max_length=200, blank=True)
    plz = models.CharField("PLZ", max_length=10, blank=True)
    ort = models.CharField("Ort", max_length=100, blank=True)
    land = models.CharField("Land", max_length=100, blank=True, help_text="Leer = Deutschland")
    telefon = models.CharField("Telefon", max_length=50, blank=True)
    mobil = models.CharField("Mobil", max_length=50, blank=True)
    email = models.EmailField("E-Mail", blank=True)
    # Die Haupt-E-Mail oben gilt für Konto, Einladungen und Serienbriefe; hier steht, unter
    # welchen Adressen die Person sonst noch erreichbar ist.
    email_weitere = models.CharField(
        "Weitere E-Mail-Adressen", max_length=500, blank=True,
        help_text="Mehrere mit Komma trennen. Post aus bintafeln (Einladung, Serienbrief) geht "
        "an die E-Mail darüber.",
    )  # fmt: skip
    webseite = models.URLField("Webseite", blank=True)
    nummer = models.PositiveIntegerField(
        "Adressnummer", null=True, blank=True, unique=True,
        help_text="Wird automatisch vergeben, außer bei Mitgliedern (die haben ihre "
        "Mitgliedsnummer).",
    )  # fmt: skip
    kategorien = models.ManyToManyField(
        AdressKategorie, blank=True, related_name="adressen", verbose_name="Kategorien"
    )
    notiz = models.TextField("Notiz", blank=True)
    # Für Personen, die mitarbeiten, das Login-Konto. Ob und wie jemand im Dienstplan/Fahrdienst
    # einteilbar ist, ergibt sich aus der Rolle des Kontos (ADR 0097), nicht mehr aus eigenen
    # Feldern. Die Verknüpfung zum Konto ist fest 1:1; das Konto bleibt das Anmelde-Objekt.
    konto = models.OneToOneField(
        "konten.Benutzer", null=True, blank=True, on_delete=models.SET_NULL,
        related_name="adresse", verbose_name="Konto",
        help_text="Das Anmelde-Konto dieser Person (für Helfer, die sich selbst anmelden).",
    )  # fmt: skip
    einwilligung_post = models.DateField(
        "Einwilligung Post seit", null=True, blank=True,
        help_text="Datum, ab dem Briefe (z. B. Serienbriefe) erlaubt sind.",
    )  # fmt: skip
    einwilligung_email = models.DateField("Einwilligung E-Mail seit", null=True, blank=True)
    veroeffentlichen = models.DateField(
        "Name darf veröffentlicht werden seit", null=True, blank=True,
        help_text="Z. B. als Spender auf der Webseite oder im Jahresbericht.",
    )  # fmt: skip
    angelegt_am = models.DateTimeField("Angelegt am", auto_now_add=True)
    geaendert_am = models.DateTimeField("Geändert am", null=True, blank=True)
    geaendert_von = models.CharField("Geändert von", max_length=150, blank=True)

    class Meta:
        verbose_name = "Adresse"
        verbose_name_plural = "Adressen"
        ordering = ["organisation", "nachname", "vorname", "pk"]

    def __str__(self):
        return self.name

    # Text aus anderen Programmen (Import, ausgelesene PDFs): Ligaturen und unsichtbare Zeichen
    # erscheinen im Druck als schwarzer Block
    TEXTFELDER = ("organisation", "vorname", "nachname", "ansprechperson", "strasse", "plz", "ort",
                  "land")  # fmt: skip

    def save(self, *args, **kwargs):
        for feld in self.TEXTFELDER:
            setattr(self, feld, zeichen.bereinigen(getattr(self, feld)))
        # Adressnummer für alle ohne Mitgliedschaft (ADR 0133). Wer gerade als Mitglied angelegt
        # wird, setzt ``als_mitglied`` – er bekommt seine Mitgliedsnummer statt einer Adressnummer.
        if (
            self.nummer is None
            and not getattr(self, "als_mitglied", False)
            and not self.mitgliedsnummer
        ):
            self.nummer = naechste_adressnummer()
        super().save(*args, **kwargs)
        self._email_ans_konto()

    def _email_ans_konto(self) -> None:
        """Adresse und Konto gehören zusammen: Die E-Mail der Adresse gilt auch fürs Konto (dorthin
        gehen Einladung und Passwort-Link, sie steht in den Team-Listen). Eine leere E-Mail löscht
        die des Kontos nicht."""
        if not self.konto_id or not self.email:
            return
        konto = self.konto
        if konto.stelle_id is None and konto.email != self.email:
            konto.email = self.email
            konto.save(update_fields=["email"])

    @property
    def mitgliedsnummer(self) -> str:
        if self.pk is None:
            return ""
        try:
            return self.mitglied.nummer
        except models.ObjectDoesNotExist:
            return ""

    @property
    def nummer_anzeige(self) -> str:
        """Die Nummer im Adressbuch: bei Mitgliedern die Mitgliedsnummer, sonst die Adressnummer."""
        return self.mitgliedsnummer or (str(self.nummer) if self.nummer else "")

    def clean(self):
        if self.art == self.Art.PERSON and not self.nachname:
            raise ValidationError({"nachname": "Bei einer Person ist der Nachname nötig."})
        if self.art == self.Art.ORGANISATION and not self.organisation:
            raise ValidationError({"organisation": "Bitte den Namen der Organisation angeben."})
        if self.art == self.Art.ORGANISATION and self.konto_id:
            raise ValidationError("Ein Konto gibt es nur bei einer Person, nicht bei einer "
                                  "Organisation.")  # fmt: skip
        try:
            weitere = emails_ordnen(self.email_weitere, self.email)
        except ValidationError as fehler:
            raise ValidationError({"email_weitere": fehler.messages}) from None
        if weitere and not self.email:
            self.email = weitere.pop(0)  # ohne Haupt-E-Mail rückt die erste nach
        self.email_weitere = ", ".join(weitere)
        if len(self.email_weitere) > 500:
            raise ValidationError({"email_weitere": "Das sind zu viele Adressen für dieses Feld."})

    @property
    def emails(self) -> list[str]:
        """Alle E-Mail-Adressen der Person, die Haupt-E-Mail zuerst."""
        weitere = [t.strip() for t in self.email_weitere.split(",") if t.strip()]
        return ([self.email] if self.email else []) + weitere

    @property
    def personenname(self) -> str:
        return " ".join(t for t in (self.vorname, self.nachname) if t)

    @property
    def mail(self) -> str:
        """E-Mail für Benachrichtigungen: die des Kontos, sonst die der Adresse."""
        return (self.konto.email if self.konto_id else "") or self.email

    @property
    def name(self) -> str:
        if self.art == self.Art.ORGANISATION:
            return self.organisation or self.personenname
        return self.personenname or self.organisation

    @property
    def anschrift_zeilen(self) -> list[str]:
        """Anschrift für Briefe und Fensterumschläge."""
        zeilen = []
        if self.art == self.Art.ORGANISATION:
            zeilen.append(self.organisation)
            if self.ansprechperson:
                zeilen.append(self.ansprechperson)
        else:
            zeilen.append(" ".join(t for t in (self.anrede, self.vorname, self.nachname) if t))
        zeilen += [self.strasse, " ".join(t for t in (self.plz, self.ort) if t), self.land]
        return [z for z in zeilen if z]


auditlog.register(Adresse, m2m_fields={"kategorien"}, exclude_fields=["geaendert_am"])
auditlog.register(AdressKategorie)
auditlog.register(AdressEinstellungen)

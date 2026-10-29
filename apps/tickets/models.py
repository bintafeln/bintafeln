"""Tickets (ADR 0087): Wer etwas findet (defektes Gerät, Fehler im Programm, Lager …), eröffnet
ein Ticket; je Kategorie bekommen die eingestellten Personen und Rollen Bescheid."""

from auditlog.registry import auditlog
from django.conf import settings
from django.contrib.auth.models import Group
from django.db import models


class TicketEinstellungen(models.Model):
    EINZIGE_ID = 1
    loeschen_nach_tagen = models.PositiveIntegerField(
        "Erledigte Tickets löschen nach (Tagen)", default=365,
        help_text="Danach kommen erledigte Tickets samt Kommentaren und Dateien weg.",
    )  # fmt: skip

    class Meta:
        verbose_name = "Ticket-Einstellungen"
        verbose_name_plural = "Ticket-Einstellungen"

    def __str__(self):
        return "Ticket-Einstellungen"

    def save(self, *args, **kwargs):
        self.pk = self.EINZIGE_ID
        super().save(*args, **kwargs)

    @classmethod
    def laden(cls) -> "TicketEinstellungen":
        return cls.objects.get_or_create(pk=cls.EINZIGE_ID)[0]


class Kategorie(models.Model):
    name = models.CharField("Name", max_length=80, unique=True)
    beschreibung = models.CharField("Beschreibung", max_length=200, blank=True,
                                    help_text="Hilft beim Wählen, z. B. „Kühlung, Waagen, "
                                    "Fahrzeuge“.")  # fmt: skip
    personen = models.ManyToManyField(
        settings.AUTH_USER_MODEL, blank=True, related_name="ticket_kategorien",
        verbose_name="Benachrichtigen: Personen",
    )  # fmt: skip
    rollen = models.ManyToManyField(Group, blank=True, related_name="ticket_kategorien",
                                    verbose_name="Benachrichtigen: Rollen")  # fmt: skip
    aktiv = models.BooleanField(
        "Aktiv", default=True, help_text="Inaktive Kategorien stehen beim Eröffnen nicht zur Wahl."
    )
    reihenfolge = models.PositiveSmallIntegerField("Reihenfolge", default=0)

    class Meta:
        ordering = ["reihenfolge", "name"]
        verbose_name = "Ticket-Kategorie"
        verbose_name_plural = "Ticket-Kategorien"

    def __str__(self):
        return self.name


class Ticket(models.Model):
    class Status(models.TextChoices):
        OFFEN = "offen", "offen"
        IN_ARBEIT = "in_arbeit", "in Arbeit"
        ERLEDIGT = "erledigt", "erledigt"

    kategorie = models.ForeignKey(Kategorie, on_delete=models.PROTECT, related_name="tickets",
                                  verbose_name="Kategorie")  # fmt: skip
    titel = models.CharField("Worum geht es?", max_length=150)
    beschreibung = models.TextField("Beschreibung", help_text="Was ist passiert, wo, seit wann?")
    status = models.CharField("Status", max_length=12, choices=Status.choices,
                              default=Status.OFFEN, db_index=True)  # fmt: skip
    erstellt_von = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                     on_delete=models.SET_NULL, related_name="tickets",
                                     verbose_name="Gemeldet von")  # fmt: skip
    erstellt_am = models.DateTimeField("Gemeldet am", auto_now_add=True)
    zustaendig = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                                   on_delete=models.SET_NULL, related_name="zustaendige_tickets",
                                   verbose_name="Zuständig")  # fmt: skip
    erledigt_am = models.DateTimeField("Erledigt am", null=True, blank=True)
    geaendert_am = models.DateTimeField("Geändert am", auto_now=True)

    class Meta:
        ordering = ["-erstellt_am"]
        verbose_name = "Ticket"
        verbose_name_plural = "Tickets"

    def __str__(self):
        return f"Ticket {self.pk}: {self.titel}"


class Kommentar(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="kommentare")
    von = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True,
                            on_delete=models.SET_NULL, verbose_name="Von")  # fmt: skip
    text = models.TextField("Kommentar")
    am = models.DateTimeField("Am", auto_now_add=True)

    class Meta:
        ordering = ["am"]
        verbose_name = "Ticket-Kommentar"
        verbose_name_plural = "Ticket-Kommentare"

    def __str__(self):
        return f"Kommentar zu Ticket {self.ticket_id}"


class Anhang(models.Model):
    """Foto oder PDF zu einem Ticket, verschlüsselt über apps.core.privatdateien."""

    ORDNER = "tickets"
    PRIVATDATEI = (ORDNER, "datei")  # Papierkorb (ADR 0073)
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name="anhaenge")
    name = models.CharField("Dateiname", max_length=150)
    datei = models.CharField(max_length=100, editable=False)
    typ = models.CharField(max_length=40, editable=False)
    am = models.DateTimeField("Hochgeladen am", auto_now_add=True)

    class Meta:
        ordering = ["am"]
        verbose_name = "Ticket-Anhang"
        verbose_name_plural = "Ticket-Anhänge"

    def __str__(self):
        return self.name


auditlog.register(Ticket, exclude_fields=["geaendert_am"])
auditlog.register(Kommentar)
auditlog.register(Kategorie, m2m_fields={"personen", "rollen"})

"""Suche im Seitenkopf (ADR 0040): ab 3 Zeichen, mit Kürzeln für einzelne Bereiche.

Ohne Kürzel sucht sie Seiten des Programms (Menüpunkte), Kunden (Vor- und Nachname,
Kundennummer), Anträge, Adressen, Mitarbeitende und das Handbuch.
Ein Kürzel mit Leerzeichen davor schränkt ein, z. B. „n bescheid“ sucht in Notizen. Jeder
Bereich erscheint nur mit dem passenden Recht; Kunden nur aus den eigenen Ausgabestellen
(ADR 0034).
"""

import re
from dataclasses import dataclass, field
from functools import lru_cache

from django.db.models import Q
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags

from apps.konten import rollen

MINDESTLAENGE = 3
JE_BEREICH = 8  # in der Liste unter dem Suchfeld
JE_BEREICH_SEITE = 50  # auf der Ergebnisseite


@dataclass(frozen=True)
class Kuerzel:
    zeichen: str
    bereich: str
    beschreibung: str
    rechte: tuple[str, ...]


KUERZEL = [
    Kuerzel("k", "kunden", "Kunden: Vor- und Nachname, Kundennummer, Abholberechtigte",
            ("kunden.liste", "kunden.ansehen", "einlass.nutzen")),
    Kuerzel("n", "notizen", "Notizen: Text", ("kunden.notizen",)),
    Kuerzel("a", "anmerkungen", "Anmerkungen zu Haushalten und Anträgen",
            ("kunden.anmerkungen", "antraege.sehen")),
    Kuerzel("s", "anschrift", "Anschrift: Straße, PLZ, Ort", ("kunden.kontakt",)),
    Kuerzel("t", "kontakt", "Telefon und E-Mail", ("kunden.kontakt",)),
    Kuerzel("d", "dokumente", "Dokumente zum Haushalt: Titel", ("kunden.dokumente",)),
    Kuerzel("an", "antraege", "Anträge: Name, Antragsnummer", ("antraege.sehen",)),
    Kuerzel("ad", "adressen", "Adressbuch: Name, Organisation, Ansprechperson, Ort, E-Mail",
            ("adressen.sehen",)),
    Kuerzel("m", "mitarbeitende", "Mitarbeitende: Name, Benutzername",
            ("mitarbeitende.verwalten",)),
    Kuerzel("p", "programm", "Programm: Seiten und Menüpunkte, z. B. „p ausgabestellen“", ()),
    Kuerzel("l", "listen", "Listen und Einstellungen: Ausgabestellen, Kundengruppen, Vorlagen, "
            "Rollen, Mitglieder, Belegnummern …", ()),
    Kuerzel("h", "hilfe", "Hilfe: Text im Handbuch", ()),
]  # fmt: skip
OHNE_KUERZEL = ("programm", "listen", "kunden", "antraege", "adressen", "mitarbeitende", "hilfe")

TITEL = {
    "programm": "Programm",
    "listen": "Listen und Einstellungen",
    "kunden": "Kunden",
    "notizen": "Notizen",
    "anmerkungen": "Anmerkungen",
    "anschrift": "Anschrift",
    "kontakt": "Telefon und E-Mail",
    "dokumente": "Dokumente",
    "antraege": "Anträge",
    "mitarbeitende": "Mitarbeitende",
    "adressen": "Adressbuch",
    "hilfe": "Hilfe",
}


@dataclass
class Treffer:
    titel: str
    url: str
    zusatz: str = ""


@dataclass
class Gruppe:
    bereich: str
    titel: str
    treffer: list[Treffer] = field(default_factory=list)
    weitere: bool = False


@dataclass
class Ergebnis:
    eingabe: str
    begriff: str = ""
    kuerzel: Kuerzel | None = None
    gruppen: list[Gruppe] = field(default_factory=list)
    zu_kurz: bool = False

    @property
    def anzahl(self) -> int:
        return sum(len(g.treffer) for g in self.gruppen)


def kuerzel_fuer(benutzer) -> list[Kuerzel]:
    return [k for k in KUERZEL if not k.rechte or rollen.hat_recht(benutzer, *k.rechte)]


def zerlegen(eingabe: str) -> tuple[Kuerzel | None, str]:
    """„n bescheid“ -> (Kürzel n, „bescheid“); ohne bekanntes Kürzel die ganze Eingabe."""
    eingabe = " ".join(eingabe.split())
    teile = eingabe.split(" ", 1)
    if len(teile) == 2:
        for k in KUERZEL:
            if teile[0].lower() == k.zeichen:
                return k, teile[1]
    return None, eingabe


def _ausschnitt(text: str, begriff: str, breite: int = 60) -> str:
    """Ein Stück Text rund um den Fundort, damit man sieht, warum etwas gefunden wurde."""
    text = " ".join(text.split())
    stelle = text.lower().find(begriff.lower())
    if stelle < 0:
        return text[: breite * 2] + ("…" if len(text) > breite * 2 else "")
    anfang = max(0, stelle - breite)
    ende = min(len(text), stelle + len(begriff) + breite)
    return ("…" if anfang else "") + text[anfang:ende] + ("…" if ende < len(text) else "")


def _haushalte(benutzer):
    from apps.kunden import zugang
    from apps.kunden.models import Haushalt

    return zugang.filtern(Haushalt.objects.all(), benutzer)


def _kunden_url(benutzer, kundennummer: str) -> str:
    if rollen.hat_recht(benutzer, "kunden.ansehen"):
        return reverse("kunden:haushalt", args=[kundennummer])
    return f"{reverse('ausgabe:empfang')}?nummer={kundennummer}"


def _nummern(benutzer):
    """Kundennummern, die das Konto aufrufen darf (für Daten an der Kundennummer)."""
    return _haushalte(benutzer).values("kundennummer")


def _kunden(benutzer, begriff, grenze):
    from apps.kunden.models import Abholer, Person

    haushalte = _haushalte(benutzer)
    passend = Q(vorname__icontains=begriff) | Q(nachname__icontains=begriff)
    personen = Person.objects.filter(passend, haushalt__in=haushalte)
    abholer = Abholer.objects.filter(passend, haushalt__in=haushalte)
    nummern = haushalte.filter(kundennummer__icontains=begriff)
    treffer, gesehen = [], set()

    def neu(h, titel, zusatz):
        if (h.pk, titel) in gesehen:
            return
        gesehen.add((h.pk, titel))
        treffer.append(Treffer(titel, _kunden_url(benutzer, h.kundennummer), zusatz))

    def gruppe(h):
        g = h.kundengruppe
        return f"{g.name}" if g else ""

    for h in nummern.select_related("kundengruppe").order_by("kundennummer")[: grenze + 1]:
        haupt = h.personen.filter(ist_hauptperson=True).first()
        neu(h, f"{h.kundennummer} · {haupt.vorname} {haupt.nachname}" if haupt
            else h.kundennummer, gruppe(h))  # fmt: skip
    for p in personen.select_related("haushalt__kundengruppe").order_by("nachname", "vorname")[
        : grenze + 1
    ]:
        h = p.haushalt
        rolle = "Hauptperson" if p.ist_hauptperson else "im Haushalt"
        neu(h, f"{p.vorname} {p.nachname} · Kunde {h.kundennummer}",
            ", ".join(x for x in (rolle, h.get_status_display(), gruppe(h)) if x))  # fmt: skip
    for a in abholer.select_related("haushalt__kundengruppe").order_by("nachname")[: grenze + 1]:
        h = a.haushalt
        neu(h, f"{a.vorname} {a.nachname} · Kunde {h.kundennummer}", "abholberechtigt")
    return treffer


def _notizen(benutzer, begriff, grenze):
    from apps.kunden.models import Notiz

    notizen = Notiz.objects.filter(text__icontains=begriff, kundennummer__in=_nummern(benutzer))
    return [
        Treffer(f"Kunde {n.kundennummer}: {_ausschnitt(n.text, begriff)}",
                _kunden_url(benutzer, n.kundennummer),
                " · ".join(x for x in (f"{timezone.localtime(n.erstellt_am):%d.%m.%Y}",
                                       n.verfasst_von) if x))
        for n in notizen.order_by("-erstellt_am")[: grenze + 1]
    ]  # fmt: skip


def _anmerkungen(benutzer, begriff, grenze):
    from apps.antraege.models import AntragAnmerkung
    from apps.kunden.models import Bemerkung

    treffer = []
    if rollen.hat_recht(benutzer, "kunden.anmerkungen"):
        for b in (
            Bemerkung.objects.filter(text__icontains=begriff, haushalt__in=_haushalte(benutzer))
            .select_related("haushalt")
            .order_by("-datum")[: grenze + 1]
        ):
            treffer.append(Treffer(
                f"Kunde {b.haushalt.kundennummer}: {_ausschnitt(b.text, begriff)}",
                _kunden_url(benutzer, b.haushalt.kundennummer), f"{b.datum:%d.%m.%Y}"))  # fmt: skip
    if rollen.hat_recht(benutzer, "antraege.sehen"):
        for a in (
            AntragAnmerkung.objects.filter(text__icontains=begriff)
            .select_related("antrag")
            .order_by("-zeitpunkt")[: grenze + 1]
        ):
            treffer.append(Treffer(
                f"Antrag {a.antrag.nummer}: {_ausschnitt(a.text, begriff)}",
                reverse("antraege:antrag", args=[a.antrag.pk]),
                f"{timezone.localtime(a.zeitpunkt):%d.%m.%Y} · {a.von}"))  # fmt: skip
    return treffer


def _haushalt_felder(benutzer, begriff, grenze, felder, beschreiben):
    passend = Q()
    for f in felder:
        passend |= Q(**{f"{f}__icontains": begriff})
    return [
        Treffer(f"Kunde {h.kundennummer}: {beschreiben(h)}",
                _kunden_url(benutzer, h.kundennummer))
        for h in _haushalte(benutzer).filter(passend).order_by("kundennummer")[: grenze + 1]
    ]  # fmt: skip


def _anschrift(benutzer, begriff, grenze):
    return _haushalt_felder(benutzer, begriff, grenze, ("strasse", "plz", "ort"),
                            lambda h: ", ".join(x for x in (h.strasse, f"{h.plz} {h.ort}".strip())
                                                if x))  # fmt: skip


def _kontakt(benutzer, begriff, grenze):
    return _haushalt_felder(benutzer, begriff, grenze, ("telefon", "email"),
                            lambda h: " · ".join(x for x in (h.telefon, h.email) if x))  # fmt: skip


def _dokumente(benutzer, begriff, grenze):
    from apps.kunden.models import HaushaltDokument

    dokumente = HaushaltDokument.objects.filter(
        titel__icontains=begriff, kundennummer__in=_nummern(benutzer)
    ).select_related("art")
    return [
        Treffer(f"Kunde {d.kundennummer}: {d.titel}", _kunden_url(benutzer, d.kundennummer),
                f"{d.art} · {timezone.localtime(d.hochgeladen_am):%d.%m.%Y}")
        for d in dokumente.order_by("-pk")[: grenze + 1]
    ]  # fmt: skip


def _antraege(benutzer, begriff, grenze):
    from apps.antraege.models import Antrag

    passend = Q(vorname__icontains=begriff) | Q(nachname__icontains=begriff)
    if begriff.isdigit():
        passend |= Q(laufnummer=int(begriff))
    return [
        Treffer(f"Antrag {a.nummer} · {a.name}", reverse("antraege:antrag", args=[a.pk]),
                f"{a.get_status_display()}{', im Papierkorb' if a.papierkorb_am else ''}")
        for a in Antrag.objects.filter(passend).order_by("-eingegangen_am")[: grenze + 1]
    ]  # fmt: skip


def _mitarbeitende(benutzer, begriff, grenze):
    from apps.konten.models import Benutzer

    passend = (Q(first_name__icontains=begriff) | Q(last_name__icontains=begriff)
               | Q(username__icontains=begriff))  # fmt: skip
    return [
        Treffer(b.get_full_name() or b.username, reverse("konten:mitarbeiter", args=[b.pk]),
                b.username + (" · gesperrt" if not b.is_active else ""))
        for b in Benutzer.objects.filter(passend).order_by("last_name", "first_name")[
            : grenze + 1
        ]
    ]  # fmt: skip


def _adressen(benutzer, begriff, grenze):
    from apps.adressen.models import Adresse

    passend = (Q(organisation__icontains=begriff) | Q(vorname__icontains=begriff)
               | Q(nachname__icontains=begriff) | Q(ansprechperson__icontains=begriff)
               | Q(ort__icontains=begriff) | Q(email__icontains=begriff))  # fmt: skip
    adressen = Adresse.objects.filter(passend).prefetch_related("kategorien")
    return [
        Treffer(a.name + (f" · {a.ort}" if a.ort else ""),
                reverse("adressen:adresse", args=[a.pk]),
                ", ".join(k.name for k in a.kategorien.all()) or a.get_art_display().split(" (")[0])
        for a in adressen.order_by("organisation", "nachname")[: grenze + 1]
    ]  # fmt: skip


def _programm(benutzer, begriff, grenze, menue=()):
    """Menüpunkte, die das Konto sieht: zuerst Treffer im Namen, dann im Bereich."""
    begriff = begriff.lower()
    im_namen, im_bereich, gesehen = [], [], set()
    for bereich in menue:
        if bereich.get("gruppen"):
            wege = [(f"{bereich['titel']} › {g['titel']}", g["eintraege"])
                    for g in bereich["gruppen"]]  # fmt: skip
        else:
            wege = [(bereich["titel"], bereich["eintraege"])]
        for weg, eintraege in wege:
            for e in eintraege:
                if e["url"] in gesehen:
                    continue
                if begriff in e["titel"].lower():
                    ziel = im_namen
                elif begriff in weg.lower():
                    ziel = im_bereich
                else:
                    continue
                gesehen.add(e["url"])
                ziel.append(Treffer(e["titel"], e["url"], f"Menü: {weg}"))
    # Name beginnt mit dem Begriff zuerst (sortiert stabil, sonst Menüreihenfolge)
    im_namen.sort(key=lambda t: not t.titel.lower().startswith(begriff))
    return (im_namen + im_bereich)[: grenze + 1]


def _listen(benutzer, begriff, grenze):
    """Einträge aus Listen und Einstellungen, je nur mit dem Recht für die verlinkte Seite."""
    from apps.adressen.models import AdressKategorie
    from apps.ausgabe.models import BeitragsfreierZeitraum
    from apps.core import module
    from apps.konten.models import Rolle
    from apps.kunden.models import (
        Ausgabestelle,
        Dokumentart,
        Einkommensart,
        Kundengruppe,
        NotizVorlage,
    )
    from apps.mitglieder.models import Mitglied
    from apps.serienbriefe.models import Vorlage
    from apps.spenden.models import Spende

    def liste(art, eintrag):
        return reverse("kunden:listeneintrag", args=[art, eintrag.pk])

    treffer = []
    if rollen.hat_recht(benutzer, "kunden.liste"):
        for a in Ausgabestelle.objects.filter(Q(name__icontains=begriff) | Q(ort__icontains=begriff)
                                              | Q(strasse__icontains=begriff)):  # fmt: skip
            treffer.append(
                Treffer(
                    a.name,
                    reverse("kunden:ausgabestelle", args=[a.pk]),
                    ", ".join(x for x in ("Ausgabestelle", a.anschrift) if x),
                )
            )
    if rollen.hat_recht(benutzer, "einstellungen.listen"):
        for g in Kundengruppe.objects.filter(
            Q(name__icontains=begriff)
            | Q(kuerzel__icontains=begriff)
            | Q(ausgabestelle__name__icontains=begriff)
        ):
            treffer.append(Treffer(str(g), liste("kundengruppen", g),
                                   " · ".join(x for x in ("Kundengruppe", g.wochentage,
                                              str(g.ausgabestelle or "")) if x)))  # fmt: skip
        quellen = [
            (Einkommensart, "bezeichnung", "einkommensarten", "Einkommensart"),
            (Dokumentart, "bezeichnung", "dokumentarten", "Dokumentart"),
            (NotizVorlage, "text", "notizvorlagen", "Notiz-Vorlage"),
            (AdressKategorie, "name", "adresskategorien", "Adresskategorie"),
            (BeitragsfreierZeitraum, "bezeichnung", "beitragsfrei", "Beitragsfreier Zeitraum"),
        ]
        for modell, feld, art, art_name in quellen:
            for e in modell.objects.filter(**{f"{feld}__icontains": begriff})[: grenze + 1]:
                treffer.append(Treffer(str(getattr(e, feld)), liste(art, e), art_name))
    if rollen.hat_recht(benutzer, "einstellungen.rollen"):
        for r in Rolle.objects.filter(
            Q(gruppe__name__icontains=begriff) | Q(beschreibung__icontains=begriff)
        ).select_related("gruppe"):
            treffer.append(
                Treffer(
                    r.gruppe.name,
                    reverse("konten:rolle", args=[r.pk]),
                    "Rolle" + (f" · {r.beschreibung}" if r.beschreibung else ""),
                )
            )
    if rollen.hat_recht(benutzer, "serienbriefe.erstellen"):
        for v in Vorlage.objects.filter(Q(name__icontains=begriff) | Q(betreff__icontains=begriff)):
            treffer.append(
                Treffer(
                    v.name,
                    reverse("serienbriefe:vorlage", args=[v.pk]),
                    f"Serienbrief-Vorlage · {v.betreff}",
                )
            )
    if rollen.hat_recht(benutzer, "mitglieder.sehen"):
        for m in Mitglied.objects.filter(nummer__icontains=begriff).select_related("adresse"):
            treffer.append(
                Treffer(
                    f"Mitglied {m.nummer} · {m.adresse.name}",
                    reverse("mitglieder:mitglied", args=[m.pk]),
                    m.art,
                )
            )
    if rollen.hat_recht(benutzer, "spenden.erfassen"):
        for sp in Spende.objects.filter(belegnummer__icontains=begriff).select_related("adresse"):
            treffer.append(Treffer(f"Spende {sp.belegnummer} · {sp.adresse.name}",
                                   reverse("spenden:bearbeiten", args=[sp.pk]),
                                   f"{sp.datum:%d.%m.%Y}" + (f" · {sp.betrag} €" if sp.betrag
                                                             else "")))  # fmt: skip
    treffer += module.suchen(benutzer, begriff, grenze)
    return treffer[: grenze + 1]


@lru_cache(maxsize=512)
def _kapiteltext(kennung: str, rechte: frozenset) -> tuple[tuple[str, str], ...]:
    """Kapitel als (Abschnitt, Text); der erste Abschnitt hat keine Überschrift."""
    html = render_to_string(f"hilfe/{kennung}.html", {"rechte": rechte})
    teile = re.split(r"<h3[^>]*>(.*?)</h3>", html, flags=re.S)
    abschnitte = [("", teile[0])] + list(zip(teile[1::2], teile[2::2], strict=True))
    return tuple((" ".join(strip_tags(u).split()), " ".join(strip_tags(t).split()))
                 for u, t in abschnitte)  # fmt: skip


def _hilfe(benutzer, begriff, grenze, menue=()):
    """Je Kapitel der erste passende Abschnitt; Treffer im Kapiteltitel zuerst."""
    from apps.core import hilfe as handbuch

    treffer = []
    rechte = frozenset(rollen.rechte_von(benutzer))
    klein = begriff.lower()
    for k in handbuch.sichtbar(benutzer):
        for abschnitt, text in _kapiteltext(k.kennung, rechte):
            if klein in f"{k.titel} {abschnitt} {text}".lower():
                titel = f"{k.titel} › {abschnitt}" if abschnitt else k.titel
                rang = 0 if klein in k.titel.lower() else 1 if klein in abschnitt.lower() else 2
                treffer.append((rang, Treffer(titel, f"{reverse('core:hilfe')}#{k.kennung}",
                                              _ausschnitt(text, begriff, 50))))  # fmt: skip
                break
    treffer.sort(key=lambda x: x[0])
    return [t for _, t in treffer][: grenze + 1]


SUCHEN = {
    "programm": _programm,
    "listen": _listen,
    "kunden": _kunden,
    "notizen": _notizen,
    "anmerkungen": _anmerkungen,
    "anschrift": _anschrift,
    "kontakt": _kontakt,
    "dokumente": _dokumente,
    "antraege": _antraege,
    "mitarbeitende": _mitarbeitende,
    "adressen": _adressen,
    "hilfe": _hilfe,
}


def suchen(benutzer, eingabe: str, grenze: int = JE_BEREICH, menue=()) -> Ergebnis:
    """``menue``: das Menü des Kontos (``apps.core.menue.menue``) für die Suche nach Seiten."""
    kuerzel, begriff = zerlegen(eingabe or "")
    ergebnis = Ergebnis(eingabe=eingabe or "", begriff=begriff, kuerzel=kuerzel)
    if len(begriff) < MINDESTLAENGE:
        ergebnis.zu_kurz = True
        return ergebnis
    erlaubt = {k.bereich for k in kuerzel_fuer(benutzer)}
    bereiche = [kuerzel.bereich] if kuerzel else list(OHNE_KUERZEL)
    for bereich in bereiche:
        if bereich not in erlaubt:
            continue
        if bereich in ("programm", "hilfe"):
            treffer = SUCHEN[bereich](benutzer, begriff, grenze, menue=menue)
        else:
            treffer = SUCHEN[bereich](benutzer, begriff, grenze)
        if treffer:
            ergebnis.gruppen.append(Gruppe(bereich, TITEL[bereich], treffer[:grenze],
                                           weitere=len(treffer) > grenze))  # fmt: skip
    return ergebnis


def direkt(benutzer, eingabe: str) -> str | None:
    """Enter mit einer genauen Kundennummer („k 10141“ oder nur „10141“): gleich zum Kunden.
    Führende Nullen sind egal (wie am Einlass); nur Haushalte, die das Konto sehen darf."""
    kuerzel, begriff = zerlegen(eingabe or "")
    if (kuerzel and kuerzel.bereich != "kunden") or not begriff:
        return None
    if "kunden" not in {k.bereich for k in kuerzel_fuer(benutzer)}:
        return None
    haushalte = _haushalte(benutzer)
    treffer = haushalte.filter(kundennummer__iexact=begriff).first()
    if treffer is None and begriff.isdigit():
        treffer = haushalte.filter(kundennummer__regex=rf"^0*{int(begriff)}$").first()
    return _kunden_url(benutzer, treffer.kundennummer) if treffer else None

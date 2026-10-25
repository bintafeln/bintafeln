"""Regeln der Warteliste (ADR 0051), übernommen aus dem bisherigen Neuanmeldungs-Programm.

Ablauf: neu → (nach einem Tag) wartend → eingeladen (Termin, Mail) → erschienen | entschuldigt
| nach N Tagen ohne Rückmeldung „Streichen möglich“ bzw. gestrichen. Daneben „Wartezeit bis“
(nicht einladen bis zu einem Datum). Aufgenommen ist, wer mit dem Aufnahme-Assistenten in den
Kundenstamm kam (Antrag erledigt mit Kundennummer).
"""

import datetime as dt

from django.db import transaction
from django.db.models import Q
from django.template.loader import render_to_string
from django.utils import timezone

from apps.antraege import aufnahme
from apps.antraege.models import Antrag, AntragAnmerkung
from apps.core import mail
from apps.core.models import TafelEinstellungen
from apps.warteliste.models import (
    DubletteIgnoriert,
    Einladung,
    Streichung,
    Termin,
    WartelisteEinstellungen,
    Wartestand,
)

S = Wartestand.Status
TAGE = ["Mo", "Di", "Mi", "Do", "Fr", "Sa", "So"]
DUBLETTE_AB = 0.85  # Namensähnlichkeit, ab der zwei Anträge als mögliche Dublette gelten


# ── Wartestände und Automatik ────────────────────────────────────────────────


def wartestaende_anlegen() -> None:
    """Jeder Antrag außerhalb des Papierkorbs bekommt einen Wartestand."""
    fehlend = Antrag.objects.filter(papierkorb_am__isnull=True, wartestand__isnull=True)
    Wartestand.objects.bulk_create([Wartestand(antrag=a) for a in fehlend],
                                   ignore_conflicts=True)  # fmt: skip


def _setzen(ws, status, **felder) -> None:
    ws.status = status
    for k, v in felder.items():
        setattr(ws, k, v)
    ws.geaendert_am = timezone.now()
    ws.save()


def automatik(heute: dt.date | None = None) -> None:
    """Status nach Fristen fortschreiben und die Streichungsliste kürzen (läuft regelmäßig)."""
    heute = heute or timezone.localdate()
    e = WartelisteEinstellungen.laden()
    wartestaende_anlegen()
    offen = Wartestand.objects.exclude(status__in=Wartestand.ABGESCHLOSSEN)
    # Aufgenommen (Aufnahme-Assistent) und abgelehnt (in den Anträgen) übernehmen
    offen.filter(antrag__status=Antrag.Status.ERLEDIGT).exclude(antrag__kundennummer="").update(
        status=S.AUFGENOMMEN, geaendert_am=timezone.now()
    )
    offen.filter(antrag__status=Antrag.Status.ABGELEHNT).update(
        status=S.GESTRICHEN, geaendert_am=timezone.now()
    )
    beginn = timezone.make_aware(dt.datetime.combine(heute, dt.time()))
    Wartestand.objects.filter(status=S.NEU, antrag__eingegangen_am__lt=beginn).update(
        status=S.WARTEND
    )
    Wartestand.objects.filter(status=S.WARTEZEIT, wartezeit_bis__lt=heute).update(
        status=S.WARTEZEIT_UM
    )
    faellig = Wartestand.objects.filter(
        termin__datum__lt=heute - dt.timedelta(days=e.streichen_nach_tagen)
    )  # fmt: skip
    if e.automatik == e.Automatik.MOEGLICH:
        faellig.filter(status=S.EINGELADEN).update(status=S.STREICHEN_MOEGLICH)
    elif e.automatik == e.Automatik.STREICHEN:
        for ws in faellig.filter(status__in=[S.EINGELADEN, S.STREICHEN_MOEGLICH]):
            streichen(ws, "Automatik", Streichung.Weg.AUTOMATIK)
    Streichung.objects.filter(
        gestrichen_am__lt=timezone.now() - dt.timedelta(days=e.streichungsliste_tage)
    ).delete()


# ── Status ───────────────────────────────────────────────────────────────────


def anmerken(antrag, text: str, von: str) -> None:
    AntragAnmerkung.objects.create(antrag=antrag, text=text, von=von)


@transaction.atomic
def streichen(ws, von: str, weg=Streichung.Weg.HAND) -> None:
    """Streichen: Eintrag in die Streichungsliste, Antrag gilt als abgelehnt."""
    a = ws.antrag
    Streichung.objects.create(antragsnummer=a.nummer, name=a.name,
                              termin_text=str(ws.termin) if ws.termin else "", weg=weg,
                              von=von)  # fmt: skip
    _setzen(ws, S.GESTRICHEN)
    if a.status != Antrag.Status.ABGELEHNT:
        a.status_setzen(Antrag.Status.ABGELEHNT, von)


def status_setzen(ws, status: str, von: str, wartezeit_bis: dt.date | None = None) -> None:
    if status == S.GESTRICHEN:
        streichen(ws, von)
        return
    if status == S.WARTEZEIT:
        if not wartezeit_bis:
            raise ValueError("Für „Wartezeit“ bitte das Datum angeben.")
        _setzen(ws, S.WARTEZEIT, wartezeit_bis=wartezeit_bis)
        anmerken(ws.antrag, f"Wartezeit bis {wartezeit_bis:%d.%m.%Y}", von)
        return
    if status == S.ENTSCHULDIGT and ws.termin:
        anmerken(ws.antrag, f"Entschuldigt für den Termin {ws.termin}", von)
    if ws.status == S.GESTRICHEN and ws.antrag.status == Antrag.Status.ABGELEHNT:
        ws.antrag.status_setzen(Antrag.Status.IN_BEARBEITUNG, von)  # Streichen zurückgenommen
    _setzen(ws, status, wartezeit_bis=None)


# ── Mails ────────────────────────────────────────────────────────────────────


def ort(termin, e=None) -> str:
    if termin and termin.ort.strip():
        return termin.ort.strip()
    e = e or WartelisteEinstellungen.laden()
    if e.ort.strip():
        return e.ort.strip()
    t = TafelEinstellungen.laden()
    return "\n".join(x for x in (t.name, t.strasse, f"{t.plz} {t.ort}".strip()) if x)


def _werte(antrag, termin, e) -> dict:
    return {
        "vorname": antrag.vorname, "nachname": antrag.nachname,
        "datum": f"{TAGE[termin.datum.weekday()]} {termin.datum:%d.%m.%Y}",
        "von": f"{termin.von:%H:%M}", "bis": f"{termin.bis:%H:%M}" if termin.bis else "",
        "ort": ort(termin, e).replace("\n", ", "),
    }  # fmt: skip


def einsetzen(vorlage: str, werte: dict) -> str:
    for k, v in werte.items():
        vorlage = vorlage.replace("{" + k + "}", v)
    return vorlage


def mail_inhalt(antrag, termin, absage=False) -> tuple[str, str, str]:
    """(Betreff, Text, HTML) der Einladung oder Absage."""
    e = WartelisteEinstellungen.laden()
    w = _werte(antrag, termin, e)
    zeit = f"{w['von']} Uhr" + (f" bis {w['bis']} Uhr" if w["bis"] else "")
    teile = {
        "betreff": einsetzen(e.absage_betreff if absage else e.betreff, w),
        "anrede": einsetzen(e.anrede, w),
        "einleitung": einsetzen(e.absage_text if absage else e.einleitung, w),
        "schluss": "" if absage else einsetzen(e.schluss, w),
        "mitbringen": [] if absage else [z.strip() for z in e.mitbringen.splitlines() if z.strip()],
        "gruss": einsetzen(e.gruss, w),
        "datum": w["datum"], "zeit": zeit, "ort": ort(termin, e), "absage": absage,
    }  # fmt: skip
    text = render_to_string("warteliste/mail.txt", teile).strip() + "\n"
    t = TafelEinstellungen.laden()
    html = render_to_string(
        "warteliste/mail.html", {**teile, "tafel": t, "tafel_name": t.name or "Tafel"}
    )
    return teile["betreff"], text, html


def _senden(antrag, termin, absage=False) -> str:
    """Leer bei Erfolg, sonst der Fehler (verständlich)."""
    if not antrag.email:
        return "keine E-Mail-Adresse"
    betreff, text, html = mail_inhalt(antrag, termin, absage)
    try:
        mail.senden(betreff, text, [antrag.email], html=html)
    except mail.MailFehler as fehler:
        return str(fehler)
    return ""


# ── Einladen und Absagen ─────────────────────────────────────────────────────


def einladen(antraege, termin, von: str, mail_senden=True, heute=None) -> list[dict]:
    """Lädt zum Termin ein; liefert je Antrag {antrag, ok, hinweis}."""
    heute = heute or timezone.localdate()
    ergebnisse = []
    for a in antraege:
        ws, _ = Wartestand.objects.get_or_create(antrag=a)
        if ws.status in Wartestand.ABGESCHLOSSEN:
            ergebnisse.append(
                {
                    "antrag": a,
                    "ok": False,
                    "hinweis": f"{ws.get_status_display()} – nicht eingeladen",
                }
            )
            continue
        if ws.status == S.WARTEZEIT and ws.wartezeit_bis and ws.wartezeit_bis >= heute:
            ergebnisse.append(
                {
                    "antrag": a,
                    "ok": False,
                    "hinweis": f"Wartezeit bis {ws.wartezeit_bis:%d.%m.%Y} – nicht eingeladen",
                }
            )
            continue
        fehler = _senden(a, termin) if mail_senden else ""
        weg = "E-Mail" if mail_senden and not fehler else "ohne Mail"
        Einladung.objects.create(antrag=a, termin=termin, termin_text=str(termin), von=von,
                                 weg=weg, fehler=fehler if mail_senden else "")  # fmt: skip
        _setzen(ws, S.EINGELADEN, termin=termin, eingeladen_am=timezone.now(), wartezeit_bis=None)
        if a.status == Antrag.Status.NEU:
            a.status_setzen(Antrag.Status.IN_BEARBEITUNG, von)
        if not mail_senden:
            hinweis = "eingeladen (ohne Mail – bitte anrufen oder Brief)"
        elif fehler:
            hinweis = f"eingeladen, Mail nicht gesendet: {fehler} – bitte anrufen oder Brief"
        else:
            hinweis = f"Einladung an {a.email} gesendet"
        ergebnisse.append({"antrag": a, "ok": not fehler, "hinweis": hinweis})
    return ergebnisse


def absagen(termin, antraege, von: str) -> list[dict]:
    """Termin für diese Antragsteller absagen: Mail, danach wieder wartend (ohne Termin)."""
    ergebnisse = []
    for a in antraege:
        ws = Wartestand.objects.filter(antrag=a, termin=termin).first()
        if ws is None:
            continue
        fehler = _senden(a, termin, absage=True)
        Einladung.objects.create(
            antrag=a, termin=termin, termin_text=str(termin), art=Einladung.Art.ABSAGE, von=von,
            weg="ohne Mail" if fehler else "E-Mail", fehler=fehler,
        )  # fmt: skip
        _setzen(ws, S.WARTEND, termin=None)
        ergebnisse.append({"antrag": a, "ok": not fehler,
                           "hinweis": f"Absage nicht gesendet: {fehler} – bitte anrufen"
                           if fehler else f"Absage an {a.email} gesendet"})  # fmt: skip
    return ergebnisse


# ── Dubletten unter den Anträgen ─────────────────────────────────────────────


def dubletten() -> list[dict]:
    """Paare offener Anträge mit sehr ähnlichem Namen (oder gleichem Geburtsdatum und Namen)."""
    antraege = list(
        Antrag.objects.filter(papierkorb_am__isnull=True)
        .exclude(wartestand__status__in=Wartestand.ABGESCHLOSSEN)
        .order_by("eingegangen_am")
    )  # fmt: skip
    ignoriert = set(DubletteIgnoriert.objects.values_list("a_id", "b_id"))
    paare = []
    for i, a in enumerate(antraege):
        for b in antraege[i + 1 :]:
            if (min(a.pk, b.pk), max(a.pk, b.pk)) in ignoriert:
                continue
            name = aufnahme.namens_aehnlichkeit(a.vorname, a.nachname, b.vorname, b.nachname)
            gleich_geb = a.geburtsdatum and a.geburtsdatum == b.geburtsdatum
            if name >= DUBLETTE_AB or (gleich_geb and name >= 0.6):
                gruende = [f"Name zu {round(name * 100)} % ähnlich"]
                if gleich_geb:
                    gruende.append("gleiches Geburtsdatum")
                if a.email and a.email.lower() == b.email.lower():
                    gruende.append("gleiche E-Mail")
                paare.append({"a": a, "b": b, "punkte": round(name * 100) + (20 if gleich_geb
                              else 0), "gruende": gruende})  # fmt: skip
    return sorted(paare, key=lambda p: -p["punkte"])


def ignorieren(a, b, benutzer) -> None:
    x, y = sorted([a.pk, b.pk])
    DubletteIgnoriert.objects.get_or_create(a_id=x, b_id=y, defaults={"von": benutzer})


@transaction.atomic
def zusammenfuehren(behalten, weg, von: str) -> None:
    """Den doppelten Antrag streichen und beim anderen vermerken."""
    anmerken(behalten, f"Hatte sich am {timezone.localtime(weg.eingegangen_am):%d.%m.%Y} "
             f"zusätzlich mit Antrag {weg.nummer} angemeldet.", von)  # fmt: skip
    ws, _ = Wartestand.objects.get_or_create(antrag=weg)
    streichen(ws, von, Streichung.Weg.DUBLETTE)


# ── Abgleich mit dem Kundenstamm ─────────────────────────────────────────────


def _alter(geburt: dt.date | None, heute: dt.date) -> int | None:
    if not geburt:
        return None
    return heute.year - geburt.year - ((heute.month, heute.day) < (geburt.month, geburt.day))


def _ausnahme(haushalt, person, e) -> str:
    feld = e.ausnahme_feld
    if feld is None or not feld.aktiv:
        return ""
    werte = [haushalt.zusatz.get(feld.schluessel)] + [
        p.zusatz.get(feld.schluessel) for p in haushalt.personen.all()]  # fmt: skip
    return feld.bezeichnung if any(w is True for w in werte) else ""


def hinweise(haushalt, person, heute, e=None) -> list[dict]:
    """Was der Treffer im Kundenstamm für den Antrag bedeutet: {text, art} (ok/info/sperr)."""
    e = e or WartelisteEinstellungen.laden()
    erg = []
    alter = _alter(person.geburtsdatum if person else None, heute)
    frei = []
    if e.ausnahme_ab_alter and alter is not None and alter >= e.ausnahme_ab_alter:
        frei.append(f"{alter} Jahre")
    if grund := _ausnahme(haushalt, person, e):
        frei.append(grund)
    if haushalt.status == haushalt.Status.GESPERRT:
        erg.append({"text": "Haushalt ist gesperrt", "art": "sperr"})
    bis = haushalt.ausweis_gueltig_bis
    if bis is None:
        erg.append({"text": "Ausweis ohne Ablaufdatum im Kundenstamm", "art": "info"})
    elif bis >= heute:
        erg.append({"text": f"Ausweis noch gültig bis {bis:%d.%m.%Y} – Verlängerung statt "
                    "Neuanmeldung", "art": "info"})  # fmt: skip
    else:
        sperre = aufnahme.monat_plus(bis, e.sperrzeit_monate, False) if e.sperrzeit_monate else bis
        if frei:
            erg.append({"text": f"Ausweis abgelaufen am {bis:%d.%m.%Y}; keine Sperrzeit "
                        f"({', '.join(frei)}) – direkt verlängern", "art": "ok"})  # fmt: skip
        elif heute < sperre:
            erg.append({"text": f"Ausweis abgelaufen am {bis:%d.%m.%Y} – Sperrzeit bis "
                        f"{sperre:%d.%m.%Y}", "art": "sperr"})  # fmt: skip
        else:
            erg.append({"text": f"Ausweis abgelaufen am {bis:%d.%m.%Y} – Sperrzeit vorbei, "
                        "Neuanmeldung möglich", "art": "ok"})  # fmt: skip
    if frei and bis and bis >= heute:
        erg.append({"text": f"Ausnahme von der Sperrzeit: {', '.join(frei)}", "art": "ok"})
    return erg


def kundenabgleich(antraege, heute=None) -> list[dict]:
    """Je Antrag die ähnlichsten Haushalte mit Hinweisen; Anträge mit Sperrzeit zuerst."""
    heute = heute or timezone.localdate()
    e = WartelisteEinstellungen.laden()
    ergebnis = []
    for a in antraege:
        treffer = aufnahme.treffer(a)
        if not treffer:
            continue
        for t in treffer:
            t["hinweise"] = hinweise(t["haushalt"], t["person"], heute, e)
        sperr = any(h["art"] == "sperr" for t in treffer for h in t["hinweise"])
        ergebnis.append({"antrag": a, "treffer": treffer, "sperr": sperr})
    return sorted(ergebnis, key=lambda x: (not x["sperr"], -x["treffer"][0]["punkte"]))


def offene_antraege():
    return (Antrag.objects.filter(papierkorb_am__isnull=True)
            .exclude(wartestand__status__in=Wartestand.ABGESCHLOSSEN)
            .filter(Q(status__in=Antrag.OFFEN)))  # fmt: skip


def kommende_termine(heute=None):
    heute = heute or timezone.localdate()
    return Termin.objects.filter(datum__gte=heute)


# ── Auskunft nach Art. 15 ────────────────────────────────────────────────────


def auskunft(antrag, pdf) -> None:
    ws = Wartestand.objects.filter(antrag=antrag).select_related("termin").first()
    einladungen = list(antrag.einladungen.all())
    if ws is None and not einladungen:
        return
    pdf.ueberschrift("Warteliste")
    if ws:
        pdf.angaben([
            ("Stand", ws.get_status_display()),
            ("Wartezeit bis", f"{ws.wartezeit_bis:%d.%m.%Y}" if ws.wartezeit_bis else ""),
            ("Termin", str(ws.termin) if ws.termin else ""),
        ])  # fmt: skip
    pdf.tabelle(["Am", "Art", "Termin", "Weg"],
                [[f"{timezone.localtime(e.gesendet_am):%d.%m.%Y %H:%M}", e.get_art_display(),
                  e.termin_text, e.weg] for e in einladungen],
                breiten=[0.2, 0.15, 0.4, 0.25])  # fmt: skip

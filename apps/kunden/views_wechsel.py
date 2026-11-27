"""Wechselwunsch eines Kunden eintragen und entscheiden (ADR 0173). Regeln in ``wechsel.py``."""

import datetime as dt

from django.contrib import messages
from django.core.exceptions import ValidationError
from django.core.validators import validate_email
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from apps.konten import rollen
from apps.kunden import wechsel, zugang
from apps.kunden.models import Haushalt, Kundengruppe, Wechselwunsch

eintragen_recht = rollen.recht_erforderlich("kunden.notizen")
entscheiden_recht = rollen.recht_erforderlich("kunden.wechsel_entscheiden")


def _zurueck(request, h) -> str:
    """Wohin es nach dem Eintragen geht: zum Einlass, wenn man von dort kam, sonst zum Haushalt."""
    if request.GET.get("von") == "einlass" or request.POST.get("von") == "einlass":
        return f"{reverse('ausgabe:empfang')}?nummer={h.kundennummer}"
    return reverse("kunden:haushalt", args=[h.kundennummer])


def _auswahl(h, werte) -> dict:
    """Was bisher gewählt ist – nur gültige Werte, damit sich der Fall Schritt für Schritt
    eingrenzt."""
    arten = dict(wechsel.arten(h))
    was = werte.get("was", "")
    if was not in arten:
        was = next(iter(arten)) if len(arten) == 1 else ""
    richtung = werte.get("richtung", "") if was == Wechselwunsch.Art.UHRZEIT else ""
    if richtung not in dict(wechsel.RICHTUNGEN):
        richtung = ""
    tage = wechsel.tage_zur_wahl(h) if was == Wechselwunsch.Art.TAG else []
    tag = werte.get("tag", "") if werte.get("tag", "") in dict(tage) else ""
    stellen = wechsel.stellen_zur_wahl(h) if was == Wechselwunsch.Art.STELLE else []
    stelle = next((s for s in stellen if str(s.pk) == werte.get("stelle", "")), None)
    fertig = bool(
        (was == Wechselwunsch.Art.UHRZEIT and richtung)
        or (was == Wechselwunsch.Art.TAG and tag)
        or (was == Wechselwunsch.Art.STELLE and stelle)
    )
    return {"arten": list(arten.items()), "was": was, "richtung": richtung, "tage": tage,
            "tag": tag, "stellen": stellen, "stelle": stelle, "fertig": fertig,
            "moeglich": wechsel.moeglichkeiten(h, was, richtung, tag, stelle.pk if stelle else None)
            if fertig else []}  # fmt: skip


@never_cache
@eintragen_recht
def wunsch(request, kundennummer):
    """„Will wechseln“: Schritt für Schritt eingrenzen, dann mit Kontaktprüfung speichern."""
    h = zugang.haushalt(request.user, kundennummer,
                        Haushalt.objects.select_related("kundengruppe__ausgabestelle"))  # fmt: skip
    offen = Wechselwunsch.objects.filter(
        kundennummer=h.kundennummer, status=Wechselwunsch.Status.OFFEN
    ).first()
    werte = request.POST if request.method == "POST" else request.GET
    wahl = _auswahl(h, werte)
    fehler = ""
    if request.method == "POST" and offen is None:
        gruppe = next((e["gruppe"] for e in wahl["moeglich"]
                       if str(e["gruppe"].pk) == request.POST.get("gruppe", "")), None)  # fmt: skip
        email = request.POST.get("email", "").strip()
        try:
            if not wahl["fertig"]:
                raise wechsel.WechselFehler("Bitte erst alle Fragen beantworten.")
            if wahl["moeglich"] and gruppe is None and request.POST.get("gruppe") != "keine":
                raise wechsel.WechselFehler("Bitte eine der freien Möglichkeiten wählen.")
            if email:
                try:
                    validate_email(email)
                except ValidationError:
                    raise wechsel.WechselFehler(
                        "Die E-Mail-Adresse ist so nicht gültig.") from None  # fmt: skip
            from apps.ausgabe.stelle import aktuelle

            wechsel.eintragen(
                h, request.user, wahl["was"], wahl["richtung"], wahl["tag"], wahl["stelle"],
                gruppe, request.POST.get("anmerkung", ""), email,
                request.POST.get("telefon", ""), bool(request.POST.get("ohne_email")),
                aktuelle(request.user),
            )  # fmt: skip
        except wechsel.WechselFehler as grund:
            fehler = str(grund)
        else:
            h.refresh_from_db()
            if h.email:
                messages.success(request, "Wechselwunsch eingetragen. Wir prüfen das; der Kunde "
                                 "wird per E-Mail benachrichtigt.")  # fmt: skip
            else:
                messages.warning(request, "Wechselwunsch eingetragen. Wir prüfen das. Achtung: "
                                 "Ohne E-Mail-Adresse können wir nicht zurückschreiben – der "
                                 "Kunde erfährt es am Einlass oder am Telefon.")  # fmt: skip
            return redirect(_zurueck(request, h))
    return render(request, "kunden/wechselwunsch.html", {
        "h": h, "offen": offen, "bisher": wechsel.gruppe_text(h.kundengruppe), **wahl,
        "richtungen": wechsel.RICHTUNGEN, "erreichbar": wechsel.erreichbar(h), "fehler": fehler,
        "von": werte.get("von", ""), "zurueck": _zurueck(request, h),
        "eingaben": request.POST if request.method == "POST" else {},
    })  # fmt: skip


@never_cache
@entscheiden_recht
def liste(request):
    """Offene Wechselwünsche zum Entscheiden, darunter die zuletzt entschiedenen."""
    alle = list(
        Wechselwunsch.objects.select_related("wunsch_gruppe__ausgabestelle", "stelle")[:300]
    )
    haushalte = {
        h.kundennummer: h
        for h in zugang.filtern(
            Haushalt.objects.filter(kundennummer__in=[w.kundennummer for w in alle])
            .select_related("kundengruppe__ausgabestelle").prefetch_related("personen"),
            request.user,
        )
    }  # fmt: skip
    offene, erledigte = [], []
    for w in alle:
        w.haushalt = haushalte.get(w.kundennummer)
        if w.status == Wechselwunsch.Status.OFFEN:
            if w.haushalt is None:
                continue  # Kunde einer anderen Ausgabestelle oder nicht mehr vorhanden
            w.ziele = wechsel.ziele(w.haushalt, w)
            w.kontakt = wechsel.erreichbar(w.haushalt)
            w.jetzt = wechsel.gruppe_text(w.haushalt.kundengruppe)
            offene.append(w)
        elif w.haushalt is not None:
            erledigte.append(w)
    return render(request, "kunden/wechselwuensche.html", {
        "offene": offene, "erledigte": erledigte[:50], "heute": timezone.localdate(),
        "tage": Wechselwunsch.AUFBEWAHREN_TAGE, "angebot_tage": wechsel.ANGEBOT_TAGE,
    })  # fmt: skip


@require_POST
@entscheiden_recht
def entscheiden(request, pk):
    w = get_object_or_404(Wechselwunsch, pk=pk)
    zugang.haushalt(request.user, w.kundennummer)  # 404/403, wenn der Kunde nicht zugänglich ist
    antwort = request.POST.get("antwort", "")
    try:
        if "ablehnen" in request.POST:
            w = wechsel.ablehnen(w, request.user, antwort)
            messages.success(request, f"Wechselwunsch zu {w.kundennummer} abgelehnt. "
                             f"E-Mail an den Kunden: {w.mail_stand}.")  # fmt: skip
        else:
            gruppe = Kundengruppe.objects.filter(pk=request.POST.get("gruppe") or 0).first()
            if gruppe is None:
                raise wechsel.WechselFehler("Bitte die neue Kundengruppe wählen.")
            try:
                ab = dt.date.fromisoformat(request.POST.get("ab", ""))
            except ValueError:
                ab = None
            if "anbieten" in request.POST:
                h = zugang.haushalt(request.user, w.kundennummer)
                if "senden" not in request.POST:
                    # erst ansehen: die Mail, wie der Kunde sie bekommt
                    ab = wechsel.angebot_pruefen(h, gruppe, ab, w)
                    return _vorschau(request, h, gruppe, ab, antwort,
                                     reverse("kunden:wechselwuensche"))  # fmt: skip
                w = wechsel.anbieten(w, request.user, gruppe, ab, antwort, _link(request))
                messages.success(request, _angeboten(w))
                return redirect("kunden:wechselwuensche")
            w = wechsel.genehmigen(w, request.user, gruppe, ab, antwort)
            messages.success(request, f"Wechselwunsch zu {w.kundennummer} genehmigt: "
                             f"{w.neue_gruppe}. E-Mail an den Kunden: {w.mail_stand}.")  # fmt: skip
    except wechsel.WechselFehler as grund:
        messages.error(request, str(grund))
    return redirect("kunden:wechselwuensche")


def _link(request):
    return lambda schluessel: request.build_absolute_uri(
        reverse("kunden:wechsel_angebot", args=[schluessel]))  # fmt: skip


def _angeboten(w) -> str:
    return (f"Platz angeboten ({w.angebot_text}). Der Kunde {w.kundennummer} hat eine E-Mail "
            f"bekommen und kann bis {w.angebot_bis:%d.%m.%Y} bestätigen; so lange ist der "
            "Platz reserviert.")  # fmt: skip


def _vorschau(request, h, gruppe, ab, zusatz, zurueck):
    """Zeigt die Mail vor dem Senden. „Jetzt senden“ schickt dieselben Angaben noch einmal an
    dieselbe Adresse, diesmal mit ``senden``."""
    return render(request, "kunden/wechsel_vorschau.html", {
        "h": h, "gruppe": gruppe, "ab": ab, "zusatz": zusatz, "zurueck": zurueck,
        "post": wechsel.angebot_vorschau(h, gruppe, ab, zusatz),
    })  # fmt: skip


@never_cache
@entscheiden_recht
def platz_anbieten(request, kundennummer):
    """Von der Tafel aus (Kundenseite): einen freien Platz per E-Mail anbieten – mit Vorschau –
    oder den Kunden für eine volle Kundengruppe vormerken."""
    h = zugang.haushalt(request.user, kundennummer,
                        Haushalt.objects.select_related("kundengruppe__ausgabestelle"))  # fmt: skip
    zurueck = reverse("kunden:haushalt", args=[h.kundennummer])
    wahl = wechsel.gruppen_zur_wahl(h)
    fehler = ""
    if request.method == "POST":
        gruppe = next((e["gruppe"] for e in wahl
                       if str(e["gruppe"].pk) == request.POST.get("gruppe", "")), None)  # fmt: skip
        zusatz = request.POST.get("antwort", "")
        try:
            ab = dt.date.fromisoformat(request.POST.get("ab", ""))
        except ValueError:
            ab = None
        try:
            if gruppe is None:
                raise wechsel.WechselFehler("Bitte eine Kundengruppe wählen.")
            if "vormerken" in request.POST:
                wechsel.vormerken(h, request.user, gruppe, zusatz)
                messages.success(request, f"Vorgemerkt für {gruppe.name}. Der Vorgang steht "
                                 "unter „Kunden → Wechselwünsche“; der Kunde hat nichts "
                                 "bekommen.")  # fmt: skip
                return redirect(zurueck)
            if "senden" not in request.POST:
                ab = wechsel.angebot_pruefen(h, gruppe, ab)
                if wechsel.offene().filter(kundennummer=h.kundennummer).exists():
                    raise wechsel.WechselFehler(
                        "Zu diesem Kunden ist schon ein Wechselwunsch offen – bitte dort "
                        "entscheiden (Kunden → Wechselwünsche).")  # fmt: skip
                return _vorschau(request, h, gruppe, ab, zusatz, request.path)
            w = wechsel.von_uns_anbieten(h, request.user, gruppe, ab, zusatz, _link(request))
            messages.success(request, _angeboten(w))
            return redirect(zurueck)
        except wechsel.WechselFehler as grund:
            fehler = str(grund)
    return render(request, "kunden/platz_anbieten.html", {
        "h": h, "wahl": wahl, "fehler": fehler, "zurueck": zurueck,
        "bisher": wechsel.gruppe_text(h.kundengruppe), "heute": timezone.localdate(),
        "erreichbar": wechsel.erreichbar(h), "eingaben": request.POST,
        "offen": wechsel.offene().filter(kundennummer=h.kundennummer).first(),
        "tage": wechsel.ANGEBOT_TAGE,
    })  # fmt: skip


@never_cache
def angebot(request, schluessel):
    """Öffentliche Seite hinter dem Link aus der Mail (ADR 0175): zeigt nur das Angebot – keinen
    Namen, keine Kundennummer – und nimmt „Ja“ oder „Nein“ entgegen. Bestätigt wird erst mit
    dem Knopf (POST): Mailprogramme, die Links von selbst öffnen, lösen so nichts aus."""
    from apps.core.models import TafelEinstellungen

    w = wechsel.angebot_finden(schluessel)
    if w is None:
        raise Http404
    fehler = ""
    if request.method == "POST" and w.angebot_laeuft:
        try:
            w = wechsel.angebot_beantworten(w, request.POST.get("antwort") == "ja")
        except wechsel.WechselFehler as grund:
            fehler = str(grund)
        else:
            return redirect("kunden:wechsel_angebot", schluessel)
    tafel = TafelEinstellungen.laden()
    # immer Deutsch, darunter die Sprache des Kunden (zur Staatsangehörigkeit der Hauptperson)
    s2 = wechsel.zweitsprache(Haushalt.objects.filter(kundennummer=w.kundennummer).first())
    t2 = wechsel.texte(s2.code) if s2 else {}
    if t2:
        t2 = {**t2, "ab": t2["ab"].format(ab=f"{w.angebot_ab or timezone.localdate():%d.%m.%Y}"),
              "bitte": t2["bitte"].format(bis=f"{w.angebot_bis:%d.%m.%Y}")}  # fmt: skip
    return render(request, "kunden/wechsel_angebot.html", {
        "w": w, "tafel": tafel, "fehler": fehler, "vorwahl": request.GET.get("antwort", ""),
        "s2": s2, "t2": t2,
    })  # fmt: skip


@require_POST
@entscheiden_recht
def angebot_zusage(request, pk):
    """Kundenseite, „Angaben“: Der Kunde hat das Angebot auf anderem Weg bestätigt (z. B. mit
    einer Antwort-Mail) – die Verwaltung trägt die Zusage ein."""
    w = get_object_or_404(Wechselwunsch, pk=pk)
    try:
        w = wechsel.angebot_zusage_eintragen(w, request.user)
    except wechsel.WechselFehler as grund:
        messages.error(request, str(grund))
    else:
        messages.success(request, f"Zusage eingetragen: {w.neue_gruppe or w.angebot_text}"
                         + (f" ab {w.ab:%d.%m.%Y}" if w.ab else "") + ".")  # fmt: skip
    return redirect("kunden:haushalt", w.kundennummer)

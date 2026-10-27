"""Import-Assistent (ADR 0078): Dateien hochladen → Spalten zuordnen → abgleichen → übernehmen."""

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied
from django.http import Http404
from django.shortcuts import redirect, render
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.http import require_POST

from apps.datenimport import abgleich, lesen, zuordnung
from apps.datenimport.models import ImportSitzung, ImportVorlage
from apps.datenimport.ziele import ZIELE, erlaubte
from apps.konten import rollen

MAX_DATEIGROESSE = 60 * 1024 * 1024  # große Kundenstämme mit allen Abholungen
VORSCHAU_ZEILEN = 5
KUNDEN_DATEINAMEN = [
    ("haushalt", "haushalte.csv"),
    ("angehoer", "personen.csv"),
    ("person", "personen.csv"),
    ("familie", "personen.csv"),
    ("abholer", "abholer.csv"),
    ("abholberecht", "abholer.csv"),
    ("sperr", "sperren.csv"),
    ("bemerk", "bemerkungen.csv"),
    ("anmerk", "bemerkungen.csv"),
    ("kundengruppe", "kundengruppen.csv"),
    ("gruppen", "kundengruppen.csv"),
    ("abholung", "abholungen.csv"),
    ("besuch", "abholungen.csv"),
    ("ausnahme", "ausnahmen.csv"),
]


def _ein_recht_noetig(ansicht):
    """Seiten des Assistenten: für alle, die mindestens ein Ziel importieren dürfen."""

    @login_required
    def pruefen(request, *args, **kwargs):
        if not erlaubte(request.user):
            raise PermissionDenied
        return ansicht(request, *args, **kwargs)

    pruefen.__name__ = ansicht.__name__
    pruefen.__doc__ = ansicht.__doc__
    return pruefen


def _sitzung(request, pk) -> ImportSitzung:
    ImportSitzung.abgelaufene_loeschen()
    sitzung = ImportSitzung.objects.filter(pk=pk, benutzer=request.user).first()
    if sitzung is None:
        raise Http404("Dieser Import ist abgelaufen oder existiert nicht mehr.")
    ziel = ZIELE.get(sitzung.ziel)
    if ziel is None or not rollen.hat_recht(request.user, ziel.recht):
        raise PermissionDenied
    return sitzung


def _art_raten(ziel, name: str) -> str:
    arten = ziel.arten()
    if ziel.kennung == "kunden":
        n = zuordnung.normalisieren(name)
        for teil, datei in KUNDEN_DATEINAMEN:
            if teil in n:
                return datei
    return arten[0].schluessel


def _vorlage(ziel, art, kopf) -> ImportVorlage | None:
    normal = [zuordnung.normalisieren(k) for k in kopf]
    passend = [
        (v.passt(normal), v) for v in ImportVorlage.objects.filter(ziel=ziel.kennung, art=art)
    ]
    passend = [p for p in passend if p[0] >= max(2, len([k for k in normal if k]) // 2)]
    return max(passend, key=lambda p: p[0])[1] if passend else None


def _vorschlag(ziel, t: dict, vorlage=None) -> None:
    kopf = t["zeilen"][t["kopf"]] if t["zeilen"] else []
    art = ziel.art(t["art"])
    if vorlage is None:
        vorlage = _vorlage(ziel, art.schluessel, kopf)
    t["vorlage"] = vorlage.name if vorlage else ""
    t["zuordnung"] = zuordnung.vorschlagen(kopf, art, vorlage.zuordnung if vorlage else None)


@_ein_recht_noetig
def start(request):
    ImportSitzung.abgelaufene_loeschen()
    ziele = erlaubte(request.user)
    gewaehlt = request.POST.get("ziel") or request.GET.get("ziel") or ziele[0].kennung
    if request.method == "POST":
        ziel = next((z for z in ziele if z.kennung == gewaehlt), None)
        dateien = request.FILES.getlist("dateien")
        if ziel is None:
            raise PermissionDenied
        if not dateien:
            messages.error(request, "Bitte mindestens eine Datei auswählen.")
        elif any(d.size > MAX_DATEIGROESSE for d in dateien):
            messages.error(
                request, "Dateien dürfen höchstens 60 MB groß sein (sonst in Teilen importieren)."
            )
        else:
            tabellen = []
            try:
                for d in dateien:
                    tabellen += [t.als_dict() for t in lesen.lesen(d.name, d.read())]
            except lesen.LeseFehler as fehler:
                messages.error(request, str(fehler))
                tabellen = None
            if tabellen:
                for t in tabellen:
                    t["kopf"] = lesen.kopfzeile_finden(t["zeilen"])
                    t["art"] = _art_raten(ziel, t["name"])
                    t["aus"] = False
                    _vorschlag(ziel, t)
                sitzung = ImportSitzung.objects.create(
                    benutzer=request.user,
                    ziel=ziel.kennung,
                    dateien=[d.name for d in dateien],
                    tabellen=tabellen,
                )
                return redirect("datenimport:zuordnen", pk=sitzung.pk)
    return render(
        request,
        "datenimport/start.html",
        {
            "ziele": ziele,
            "gewaehlt": gewaehlt,
            "sitzungen": ImportSitzung.objects.filter(benutzer=request.user),
        },
    )


def _ansicht_tabelle(ziel, ti, t):
    """Daten für die Zuordnungsseite: je Spalte Überschrift, Beispiele und Wahl."""
    art = ziel.art(t["art"])
    kopf = t["zeilen"][t["kopf"]] if t["zeilen"] else []
    daten = [z for z in t["zeilen"][t["kopf"] + 1 :] if any(z)]
    spalten = []
    for ci, k in enumerate(kopf):
        beispiele = [z[ci] for z in daten if ci < len(z) and z[ci]][:3]
        spalten.append(
            {
                "i": ci,
                "kopf": k,
                "beispiele": beispiele,
                "wahl": t["zuordnung"][ci] if ci < len(t["zuordnung"]) else "",
            }
        )
    fehlend = zuordnung.fehlende_pflicht(art, t["zuordnung"])
    return {
        "i": ti,
        "name": t["name"],
        "art": art,
        "kopf": t["kopf"],
        "aus": t.get("aus"),
        "hinweise": t.get("hinweise", []),
        "spalten": spalten,
        "anzahl": len(daten),
        "vorlage": t.get("vorlage", ""),
        "fehlend": fehlend,
        "vorlagen": ImportVorlage.objects.filter(ziel=ziel.kennung, art=art.schluessel),
        "titelzeilen": t["zeilen"][: t["kopf"]][:3],
    }


def _zeilen(t) -> list[tuple[int, dict]]:
    """Datenzeilen nach der Zuordnung als (Zeilennummer in der Datei, {Feld: Text})."""
    ergebnis = []
    for nummer, werte in enumerate(t["zeilen"][t["kopf"] + 1 :], start=t["kopf"] + 2):
        if any(werte):
            ergebnis.append((nummer, zuordnung.umsetzen(werte, t["zuordnung"])))
    return ergebnis


def _uebernehmen_formular(request, ziel, sitzung) -> bool:
    """Speichert Art, Kopfzeile und Zuordnung aus dem Formular. Wahr, wenn sich Art oder
    Kopfzeile geändert haben (dann wird neu vorgeschlagen)."""
    neu_raten = False
    for ti, t in enumerate(sitzung.tabellen):
        art = request.POST.get(f"a-{ti}", t["art"])
        try:
            kopf = max(
                0, min(int(request.POST.get(f"k-{ti}", t["kopf"] + 1)) - 1, len(t["zeilen"]) - 1)
            )
        except ValueError:
            kopf = t["kopf"]
        t["aus"] = request.POST.get(f"aus-{ti}") == "1"
        vorlage_pk = request.POST.get(f"v-{ti}")
        if art != t["art"] or kopf != t["kopf"]:
            t["art"], t["kopf"] = ziel.art(art).schluessel, kopf
            _vorschlag(ziel, t)
            neu_raten = True
            continue
        if vorlage_pk and request.POST.get("aktion") == f"vorlage-{ti}":
            vorlage = ImportVorlage.objects.filter(pk=vorlage_pk, ziel=ziel.kennung).first()
            if vorlage:
                _vorschlag(ziel, t, vorlage)
                neu_raten = True
                continue
        gueltig = {f.schluessel for f in ziel.art(t["art"]).alle_felder}
        breite = len(t["zeilen"][t["kopf"]]) if t["zeilen"] else 0
        t["zuordnung"] = [
            w if (w := request.POST.get(f"z-{ti}-{ci}", "")) in gueltig else ""
            for ci in range(breite)
        ]
        name = request.POST.get(f"vn-{ti}", "").strip()[:100]
        if name:
            kopf_normal = [zuordnung.normalisieren(k) for k in t["zeilen"][t["kopf"]]]
            ImportVorlage.objects.update_or_create(
                ziel=ziel.kennung,
                art=t["art"],
                name=name,
                defaults={
                    "zuordnung": {
                        k: w for k, w in zip(kopf_normal, t["zuordnung"], strict=False) if k and w
                    }
                },
            )
            t["vorlage"] = name
    return neu_raten


def _kunden_pruefen(request, sitzung, ziel):
    """Kundenstamm: Tabellen ins Importformat umschreiben und wie gewohnt prüfen."""
    from apps.kunden import importieren
    from apps.kunden.models import ImportVorbereitung

    je_art: dict[str, list] = {}
    herkunft: dict[str, list] = {}
    zugeordnet: dict[str, set] = {}
    for t in sitzung.tabellen:
        if t.get("aus"):
            continue
        # auch ohne Datenzeilen: eine leere Haushalte-Liste ist ein gültiger Vollaustausch
        je_art.setdefault(t["art"], [])
        zugeordnet.setdefault(t["art"], set()).update(z for z in t["zuordnung"] if z)
        for nummer, werte in _zeilen(t):
            je_art.setdefault(t["art"], []).append(werte)
            herkunft.setdefault(t["art"], []).append((t["name"], nummer))
    dateien = {
        art: ziel.neutral(ziel.art(art), zeilen, zugeordnet[art]) for art, zeilen in je_art.items()
    }
    ergebnis = importieren.pruefen(dateien)
    for m in ergebnis.bericht:  # Zeilen der umgeschriebenen Datei → Zeile der Originaldatei
        quelle = herkunft.get(m["datei"])
        if quelle and m["zeile"] and 2 <= m["zeile"] < len(quelle) + 2:
            name, nummer = quelle[m["zeile"] - 2]
            m["datei"], m["zeile"] = f"{name} ({m['datei']})", nummer
    if ergebnis.daten is None:
        return importieren.bericht_gruppiert(ergebnis.bericht)
    vorbereitung = ImportVorbereitung.objects.create(
        erstellt_von=request.user,
        dateien=sitzung.dateien,
        pruefsumme=ergebnis.pruefsumme,
        daten=ergebnis.daten,
        bericht=ergebnis.bericht,
    )
    sitzung.delete()
    return vorbereitung


@_ein_recht_noetig
def zuordnen(request, pk):
    sitzung = _sitzung(request, pk)
    ziel = ZIELE[sitzung.ziel]
    bericht = None
    if request.method == "POST":
        neu_raten = _uebernehmen_formular(request, ziel, sitzung)
        sitzung.save(update_fields=["tabellen"])
        if request.POST.get("aktion") == "weiter" and not neu_raten:
            aktiv = [t for t in sitzung.tabellen if not t.get("aus")]
            fehlend = [
                (t["name"], f.bezeichnung)
                for t in aktiv
                for f in zuordnung.fehlende_pflicht(ziel.art(t["art"]), t["zuordnung"])
            ]
            if not aktiv:
                messages.error(request, "Bitte mindestens eine Tabelle importieren.")
            elif fehlend:
                messages.error(
                    request, "Pflichtfelder fehlen: " + "; ".join(f"{n}: {b}" for n, b in fehlend)
                )
            elif ziel.kennung == "kunden":
                ergebnis = _kunden_pruefen(request, sitzung, ziel)
                if not isinstance(ergebnis, list):
                    return redirect("kunden:import_vorschau", pk=ergebnis.pk)
                bericht = ergebnis
            else:
                saetze, meldungen = [], []
                for t in aktiv:
                    s, m = ziel.bereinigen(ziel.art(t["art"]), _zeilen(t), t["name"])
                    saetze += s
                    meldungen += m
                sitzung.saetze, sitzung.meldungen = saetze, meldungen
                sitzung.plan = ziel.planen(saetze, request.user).als_dict()
                sitzung.save(update_fields=["saetze", "meldungen", "plan"])
                return redirect("datenimport:abgleich", pk=sitzung.pk)
        elif request.POST.get("aktion") != "weiter":
            return redirect("datenimport:zuordnen", pk=sitzung.pk)
    return render(
        request,
        "datenimport/zuordnen.html",
        {
            "sitzung": sitzung,
            "ziel": ziel,
            "bericht": bericht,
            "tabellen": [_ansicht_tabelle(ziel, ti, t) for ti, t in enumerate(sitzung.tabellen)],
            "arten": ziel.arten(),
        },
    )


def _meldungen_gruppiert(meldungen):
    gruppen: dict[tuple, dict] = {}
    for m in meldungen:
        g = gruppen.setdefault((m["stufe"], m["tabelle"], m["text"]), {**m, "zeilen": []})
        g["zeilen"].append(m["zeile"])
    for g in gruppen.values():
        g["anzahl"] = len(g["zeilen"])
        g["zeilen_kurz"] = ", ".join(map(str, g["zeilen"][:15])) + (
            f" … (+{len(g['zeilen']) - 15})" if len(g["zeilen"]) > 15 else ""
        )
    return sorted(gruppen.values(), key=lambda g: (g["stufe"] != "fehler", g["tabelle"]))


def modus_von(request) -> str:
    modus = request.POST.get("modus") or request.GET.get("modus") or abgleich.AKTUALISIEREN
    return modus if modus in abgleich.MODI else abgleich.AKTUALISIEREN


@_ein_recht_noetig
def abgleich_ansehen(request, pk):
    sitzung = _sitzung(request, pk)
    ziel = ZIELE[sitzung.ziel]
    if sitzung.plan is None:
        return redirect("datenimport:zuordnen", pk=sitzung.pk)
    modus = modus_von(request)
    if request.method == "POST":
        entscheidung = abgleich.entscheiden(sitzung.plan, modus, request.POST, ziel.aktionen)
        hinweise = ziel.anwenden(entscheidung, request.user)
        if entscheidung.ausgelassen:
            hinweise.append(f"{entscheidung.ausgelassen} mögliche Dubletten ausgelassen")
        sitzung.delete()
        messages.success(request, f"{ziel.titel} importiert: " + ", ".join(hinweise) + ".")
        return redirect(ziel.zurueck[0])
    plan = abgleich.vorgaben(sitzung.plan, modus, ziel.aktionen)
    return render(
        request,
        "datenimport/abgleich.html",
        {
            "sitzung": sitzung,
            "ziel": ziel,
            "plan": plan,
            "modus": modus,
            "modi": abgleich.MODI.items(),
            "aktionen": ziel.aktionen,
            "max_anzeige": abgleich.MAX_ANZEIGE,
            "meldungen": _meldungen_gruppiert(sitzung.meldungen),
            "aktion_url": request.path,
        },
    )


@require_POST
@_ein_recht_noetig
def verwerfen(request, pk):
    _sitzung(request, pk).delete()
    messages.info(request, "Import verworfen. Die hochgeladenen Daten wurden gelöscht.")
    return redirect("datenimport:start")


@require_POST
@_ein_recht_noetig
def vorlage_loeschen(request, pk):
    from apps.core import papierkorb

    vorlage = ImportVorlage.objects.filter(pk=pk).first()
    ziel = ZIELE.get(vorlage.ziel) if vorlage else None
    if vorlage is None or ziel is None or not rollen.hat_recht(request.user, ziel.recht):
        raise Http404
    papierkorb.loeschen(request.user, "Importvorlage", vorlage.name, vorlage, recht=ziel.recht)
    messages.success(request, f"Vorlage „{vorlage.name}“ in den Papierkorb gelegt.")
    weiter = request.POST.get("weiter", "")
    if not url_has_allowed_host_and_scheme(weiter, {request.get_host()}):
        weiter = ""
    return redirect(weiter or "datenimport:start")

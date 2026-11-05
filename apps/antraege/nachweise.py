"""Hochgeladene Nachweise über einen Formularfehler hinweg behalten (ADR 0105).

Beim Absenden landen die Dateien verschlüsselt als ``AntragEntwurfNachweis`` (an die Sitzung
gebunden). Schlägt die Prüfung an einem anderen Feld fehl, zeigt das Formular sie wieder an, statt
sie zu vergessen; beim erfolgreichen Absenden werden daraus die ``AntragAnhang`` des Antrags.
Liegen gebliebene Entwürfe räumt ``models.fristen_anwenden`` nach einem Tag weg (Datenschutz).
"""

import datetime as dt

from django.utils import timezone

from apps.antraege.forms import ANHANG_TYPEN, MAX_ANHAENGE, MAX_MB
from apps.antraege.models import ANHANG_ORDNER, AntragAnhang, AntragEntwurfNachweis
from apps.core import privatdateien


def _schluessel(request) -> str:
    if not request.session.session_key:
        request.session.create()
    return request.session.session_key


def eintraege(request):
    """Die schon hochgeladenen Nachweis-Entwürfe dieser Sitzung (für die Anzeige)."""
    key = request.session.session_key
    if not key:
        return AntragEntwurfNachweis.objects.none()
    return AntragEntwurfNachweis.objects.filter(sitzung=key)


def hinzufuegen(request, dateien, t) -> list[str]:
    """Legt neue Uploads verschlüsselt als Entwürfe ab; liefert Fehlermeldungen (Typ, Größe,
    Anzahl). Bereits abgelegte Entwürfe zählen zur Höchstzahl mit."""
    fehler = []
    key = _schluessel(request)
    vorhanden = AntragEntwurfNachweis.objects.filter(sitzung=key).count()
    for datei in dateien:
        if vorhanden >= MAX_ANHAENGE:
            fehler.append(t["fehler_datei_anzahl"].format(anzahl=MAX_ANHAENGE))
            break
        if datei.content_type not in ANHANG_TYPEN:
            fehler.append(t["fehler_datei_typ"])
            continue
        if datei.size > MAX_MB * 1024 * 1024:
            fehler.append(t["fehler_datei_gross"].format(mb=MAX_MB))
            continue
        name = privatdateien.speichern(ANHANG_ORDNER, datei, typen=ANHANG_TYPEN, max_mb=MAX_MB)
        AntragEntwurfNachweis.objects.create(
            sitzung=key, name=datei.name[:200], datei=name,
            typ=datei.content_type, groesse=datei.size,
        )  # fmt: skip
        vorhanden += 1
    return list(dict.fromkeys(fehler))  # jede Meldung höchstens einmal


def entfernen(request, pk) -> None:
    """Einen Entwurf dieser Sitzung wieder wegnehmen (samt verschlüsselter Datei)."""
    key = request.session.session_key
    entwurf = key and AntragEntwurfNachweis.objects.filter(sitzung=key, pk=pk).first()
    if entwurf:
        privatdateien.loeschen(ANHANG_ORDNER, entwurf.datei)
        entwurf.delete()


def anhaengen(request, antrag) -> None:
    """Macht aus den Entwürfen der Sitzung die Nachweise des Antrags; die Dateien bleiben liegen
    (sie gehören jetzt dem Antrag)."""
    key = request.session.session_key
    if not key:
        return
    entwuerfe = AntragEntwurfNachweis.objects.filter(sitzung=key)
    AntragAnhang.objects.bulk_create([
        AntragAnhang(antrag=antrag, name=e.name, datei=e.datei, typ=e.typ, groesse=e.groesse)
        for e in entwuerfe
    ])  # fmt: skip
    entwuerfe.delete()  # nur die Entwurf-Zeilen, nicht die Dateien


def aufraeumen(jetzt=None) -> int:
    """Entwürfe, die länger als einen Tag liegen, samt Dateien löschen; liefert die Zahl."""
    jetzt = jetzt or timezone.now()
    grenze = jetzt - dt.timedelta(days=1)
    alt = list(AntragEntwurfNachweis.objects.filter(erstellt_am__lt=grenze))
    for e in alt:
        privatdateien.loeschen(ANHANG_ORDNER, e.datei)
    AntragEntwurfNachweis.objects.filter(erstellt_am__lt=grenze).delete()
    return len(alt)

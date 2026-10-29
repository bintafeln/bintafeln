"""Papierkorb für gelöschte Daten (ADR 0073).

Löschen in der Oberfläche läuft über ``loeschen()``: Es sammelt wie Django selbst alles ein, was
mit dem Datensatz gelöscht wird (Personen eines Haushalts, Notizen …), legt eine Kopie als
``PapierkorbEintrag`` ab und löscht dann. Verschlüsselte Dateien bleiben liegen, bis der Eintrag
endgültig gelöscht wird. ``wiederherstellen()`` legt alles mit denselben Nummern wieder an.
Nach ``TafelEinstellungen.papierkorb_tage`` löscht ``fristen_anwenden()`` endgültig.

Modelle mit verschlüsselter Datei nennen sie in ``PRIVATDATEI = (ordner, feld)``.
Löschfristen und der Import löschen weiter direkt: Sie setzen Aufbewahrungsregeln um.
"""

import datetime as dt
import json

from django.apps import apps
from django.core import serializers
from django.db import IntegrityError, connection, transaction
from django.db.models import QuerySet
from django.db.models.deletion import Collector
from django.utils import timezone

from apps.core import privatdateien
from apps.core.models import PapierkorbEintrag, TafelEinstellungen


class PapierkorbFehler(ValueError):
    pass


def _gruppen(objekte):
    """Instanzen nach Modell gruppiert (``Collector.collect`` will je Aufruf ein Modell)."""
    einzeln = {}
    for o in objekte:
        if isinstance(o, QuerySet):
            yield o
        elif o is not None:
            einzeln.setdefault(type(o), []).append(o)
    yield from einzeln.values()


def _stelle(kundennummer: str):
    """Ausgabestelle des Haushalts: Konten mit Zuordnung sehen nur deren Einträge (ADR 0034)."""
    from apps.kunden.models import Haushalt

    h = Haushalt.objects.filter(kundennummer=kundennummer).select_related("kundengruppe").first()
    return h.kundengruppe.ausgabestelle_id if h and h.kundengruppe_id else None


def loeschen(benutzer, art: str, bezeichnung: str, *objekte, recht: str,
             kundennummer: str = "") -> PapierkorbEintrag:  # fmt: skip
    """Löscht ``objekte`` (Instanzen oder QuerySets) samt allem, was daran hängt, in den Papierkorb.

    ``recht``: wer den Eintrag sehen und wiederherstellen darf; ``kundennummer`` bei Daten zu
    einem Haushalt. Löst wie ``delete()`` ``ProtectedError`` aus, wenn noch etwas darauf
    verweist; dann wird nichts gelöscht."""
    with transaction.atomic():
        sammler = Collector(using="default")
        for gruppe in _gruppen(objekte):
            sammler.collect(gruppe)
        instanzen = [i for menge in sammler.data.values() for i in menge]
        instanzen += [i for qs in sammler.fast_deletes for i in qs]
        verweise = []
        for (feld, _), mengen in sammler.field_updates.items():
            for menge in mengen:
                paare = (menge.values_list("pk", feld.attname) if hasattr(menge, "values_list")
                         else [(o.pk, getattr(o, feld.attname)) for o in menge])  # fmt: skip
                modell = feld.model._meta.label_lower
                verweise += [{"modell": modell, "pk": pk, "feld": feld.attname, "wert": wert}
                             for pk, wert in paare]  # fmt: skip
        dateien = []
        for i in instanzen:
            if (ziel := getattr(type(i), "PRIVATDATEI", None)) and getattr(i, ziel[1]):
                dateien.append([ziel[0], getattr(i, ziel[1])])
        eintrag = PapierkorbEintrag.objects.create(
            art=art, bezeichnung=bezeichnung[:300], recht=recht, kundennummer=kundennummer,
            stelle_id=_stelle(kundennummer) if kundennummer else None,
            geloescht_von=benutzer.get_username() if benutzer else "",
            daten=json.loads(serializers.serialize("json", instanzen)),
            verweise=verweise, dateien=dateien,
        )  # fmt: skip
        sammler.delete()
    return eintrag


def wiederherstellen(eintrag: PapierkorbEintrag, benutzer=None) -> None:
    """Legt alles wieder an; bei einem Konflikt bleibt der Eintrag und es gibt eine Meldung.

    Eine Rolle holt nur zurück, wer alle ihre Rechte selbst hat (wie beim Bearbeiten)."""
    from apps.konten import rollen

    try:
        objekte = list(serializers.deserialize("json", json.dumps(eintrag.daten)))
    except serializers.base.DeserializationError as fehler:
        raise PapierkorbFehler("Die Daten passen nach einem Update nicht mehr zum Programm und "
                               "lassen sich nicht wiederherstellen.") from fehler  # fmt: skip
    for o in objekte:
        modell = type(o.object)
        if (benutzer is not None and modell._meta.label_lower == "konten.rolle"
                and not set(o.object.rechte) <= rollen.rechte_von(benutzer)):  # fmt: skip
            raise PapierkorbFehler("Diese Rolle hat Rechte, die Sie nicht haben; nur jemand mit "
                                   "allen diesen Rechten kann sie wiederherstellen.")  # fmt: skip
        if modell._base_manager.filter(pk=o.object.pk).exists():
            raise PapierkorbFehler(f"{modell._meta.verbose_name} „{o.object}“ gibt es schon "
                                   "wieder; nichts wiederhergestellt.")  # fmt: skip
    try:
        with transaction.atomic():
            for o in objekte:
                # Zuordnungen (ManyToMany) kommen als eigene Zeilen der Zwischentabelle mit;
                # die Liste am Datensatz würde sie ein zweites Mal anlegen
                o.m2m_data = {}
                o.save()
            for v in eintrag.verweise:
                modell = apps.get_model(v["modell"])
                modell._base_manager.filter(pk=v["pk"], **{v["feld"]: None}).update(
                    **{v["feld"]: v["wert"]})  # fmt: skip
            with connection.cursor() as c:  # Verweise jetzt prüfen, nicht erst beim Commit
                c.execute("SET CONSTRAINTS ALL IMMEDIATE")
                c.execute("SET CONSTRAINTS ALL DEFERRED")
            eintrag.delete()
    except IntegrityError as fehler:
        raise PapierkorbFehler(
            "Lässt sich nicht wiederherstellen, weil inzwischen etwas dazu fehlt oder doppelt "
            "wäre (z. B. eine gelöschte Kundengruppe oder eine neu vergebene Kundennummer)."
        ) from fehler


def endgueltig_loeschen(eintrag: PapierkorbEintrag) -> None:
    dateien = list(eintrag.dateien)
    eintrag.delete()
    transaction.on_commit(lambda: [privatdateien.loeschen(o, n) for o, n in dateien])


def endgueltig_am(eintrag: PapierkorbEintrag, tage: int) -> dt.date:
    """Tag, an dem der Eintrag endgültig gelöscht wird."""
    return timezone.localdate(eintrag.geloescht_am) + dt.timedelta(days=tage)


def fristen_anwenden(jetzt=None) -> int:
    """Einträge, die länger als eingestellt im Papierkorb liegen, endgültig löschen."""
    jetzt = jetzt or timezone.now()
    grenze = jetzt - dt.timedelta(days=TafelEinstellungen.laden().papierkorb_tage)
    alte = list(PapierkorbEintrag.objects.filter(geloescht_am__lt=grenze))
    for e in alte:
        endgueltig_loeschen(e)
    return len(alte)


def sichtbar(benutzer, eintraege=None):
    """Einträge, die das Konto sehen darf: gleiches Recht wie beim Löschen, bei Kunden auch die
    Zuordnung zu Ausgabestellen (ADR 0034)."""
    from apps.konten import rollen
    from apps.kunden import zugang

    eintraege = PapierkorbEintrag.objects.all() if eintraege is None else eintraege
    rechte = {r for r in eintraege.values_list("recht", flat=True).distinct()
              if rollen.hat_recht(benutzer, r)}  # fmt: skip
    eintraege = eintraege.filter(recht__in=rechte)
    eigene = zugang.stellen(benutzer)
    if eigene is not None:
        eintraege = eintraege.exclude(kundennummer="").filter(
            stelle_id__in=[s.pk for s in eigene]) | eintraege.filter(kundennummer="")  # fmt: skip
    return eintraege


def inhalt(eintrag: PapierkorbEintrag) -> list[dict]:
    """Zum Ansehen: je Datensatz Art und Felder mit lesbaren Namen."""
    ergebnis = []
    for d in eintrag.daten:
        try:
            meta = apps.get_model(d["model"])._meta
        except LookupError:
            meta = None
        felder = []
        for name, wert in d["fields"].items():
            if wert in ("", None, [], {}):
                continue
            try:
                feld = meta.get_field(name) if meta else None
            except Exception:  # noqa: BLE001 – Feld gibt es nach einem Update nicht mehr
                feld = None
            titel = str(feld.verbose_name) if feld else name
            felder.append((titel[:1].upper() + titel[1:], _lesbar(feld, wert)))
        art = str(meta.verbose_name) if meta else d["model"]
        ergebnis.append({"art": art, "pk": d["pk"], "felder": felder})
    return ergebnis


def _lesbar(feld, wert):
    """Wert aus der gespeicherten Kopie so, wie man ihn in der Oberfläche liest: Datum deutsch,
    ja/nein, Auswahl als Text, Verweise mit Namen (gibt es den Datensatz nicht mehr: „Nr. …“)."""
    from django.db import models
    from django.utils.dateparse import parse_date, parse_datetime

    if feld is None:
        return wert
    try:
        if isinstance(feld, models.DateTimeField):
            return timezone.localtime(parse_datetime(wert)).strftime("%d.%m.%Y %H:%M")
        if isinstance(feld, models.DateField):
            return parse_date(wert).strftime("%d.%m.%Y")
        if isinstance(feld, models.BooleanField):
            return "ja" if wert else "nein"
        if feld.choices:
            return str(dict(feld.flatchoices).get(wert, wert))
        if isinstance(feld, models.DecimalField):
            return str(wert).replace(".", ",")
        if feld.is_relation:
            ziel = feld.related_model._default_manager
            if isinstance(wert, list):
                namen = {o.pk: str(o) for o in ziel.filter(pk__in=wert)}
                return ", ".join(namen.get(pk, f"Nr. {pk}") for pk in wert)
            obj = ziel.filter(pk=wert).first()
            return str(obj) if obj else f"Nr. {wert}"
    except (TypeError, ValueError, AttributeError):
        return wert
    if isinstance(wert, dict):
        return ", ".join(f"{k}: {v}" for k, v in wert.items())
    return wert

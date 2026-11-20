"""Knöpfe und Felder, die mit ``form="…"`` an einem Formular hängen, brauchen dieses Formular auf
derselben Seite – sonst passiert beim Klicken nichts (so fehlte es in den Team-Listen hinter
„Herunterladen …“). Der Test geht mit den erfundenen Demo-Daten durch das ganze Programm."""

import re
from html.parser import HTMLParser

import pytest
from django.test import Client
from django.utils import timezone

from apps.core import demo, module
from apps.core.models import TafelEinstellungen

# Bewusst an kein Formular gebunden (Eingaben, die nur JavaScript liest)
OHNE_FORMULAR = {"kein-formular"}
# Abmelden, Rücksetzen und Ähnliches nicht anklicken
NICHT_FOLGEN = ("/abmelden", "/demo", "/admin/", "/static/", "/media/")
HOECHSTENS = 1500


class _Seite(HTMLParser):
    def __init__(self):
        super().__init__()
        self.formulare, self.verweise, self.links = set(), {}, set()

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "form" and a.get("id"):
            self.formulare.add(a["id"])
        elif a.get("form"):
            self.verweise.setdefault(a["form"], f"<{tag} name={a.get('name')!r}>")
        for name in ("href", "hx-get"):
            ziel = a.get(name) or ""
            if ziel.startswith("/") and not ziel.startswith("//"):
                self.links.add(ziel.split("#")[0])


def _muster(adresse: str) -> str:
    """Eine Seite je Art: Nummern und Werte der Adresse zählen nicht."""
    pfad, _, abfrage = adresse.partition("?")
    namen = sorted({teil.split("=")[0] for teil in abfrage.split("&") if teil})
    return re.sub(r"\d+", "N", pfad) + "?" + "&".join(namen)


@pytest.mark.django_db
def test_jeder_verweis_hat_sein_formular(settings, django_user_model, anmelden):
    settings.DEMO, settings.DEMO_PASSWORT = True, "Demo-Passwort-erfunden-1"
    demo.anlegen(timezone.localdate())
    t = TafelEinstellungen.laden()
    t.module = [m.kennung for m in module.alle()]
    t.save()
    client = anmelden(Client(), django_user_model.objects.get(username="demo-admin"))

    offen, gesehen, fehler, seiten = ["/"], set(), [], 0
    while offen and seiten < HOECHSTENS:
        adresse = offen.pop()
        muster = _muster(adresse)
        if muster in gesehen or any(teil in adresse for teil in NICHT_FOLGEN):
            continue
        gesehen.add(muster)
        antwort = client.get(adresse)
        if antwort.status_code != 200 or "text/html" not in antwort.get("Content-Type", ""):
            continue
        seiten += 1
        seite = _Seite()
        seite.feed(antwort.content.decode())
        for name, wer in seite.verweise.items():
            if name not in seite.formulare and name not in OHNE_FORMULAR:
                fehler.append(f'{adresse}: {wer} hängt an form="{name}", das Formular fehlt')
        offen.extend(seite.links)
    assert seiten > 150, f"nur {seiten} Seiten besucht"
    assert not fehler, "\n".join(sorted(set(fehler)))

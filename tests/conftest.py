import re

import pytest
from django.contrib.auth.models import Group
from django_otp import DEVICE_ID_SESSION_KEY
from django_otp.plugins.otp_totp.models import TOTPDevice

from apps.konten import rollen

PASSWORT = "Sicher-genug-123"


@pytest.fixture(autouse=True)
def medien_verzeichnis(settings, tmp_path):
    settings.MEDIA_ROOT = tmp_path / "media"


@pytest.fixture(autouse=True)
def leerer_cache():
    """Zähler wie die Fehlversuche bei der Anmeldung gelten nur innerhalb eines Tests."""
    from django.core.cache import cache

    cache.clear()


@pytest.fixture(autouse=True)
def ohne_feste_merkmale(request):
    """Die mitgelieferten Merkmale (ADR 0071) legt eine Migration an. Ältere Tests legen ihre
    Zusatzfelder selbst an; dort stören sie. Tests mit @pytest.mark.merkmale behalten sie."""
    marker = request.node.get_closest_marker("django_db")
    if marker and marker.kwargs.get("transaction") or "transactional_db" in request.fixturenames:
        return  # löscht ohnehin alles hinterher; ein Löschen hier stört das Leeren
    if request.node.get_closest_marker("merkmale"):
        return
    if "db" not in request.fixturenames and not marker:
        return
    request.getfixturevalue("db")
    from django.db import connection

    from apps.core.auswahl import FESTE_MERKMALE
    from apps.kunden.models import Zusatzfeld

    Zusatzfeld.objects.filter(schluessel__in=[s for s, *_ in FESTE_MERKMALE]).delete()
    with connection.cursor() as c:  # offene Prüfungen gleich erledigen (sonst scheitert „flush“)
        c.execute("SET CONSTRAINTS ALL IMMEDIATE")
        c.execute("SET CONSTRAINTS ALL DEFERRED")


@pytest.fixture
def benutzer_mit_rolle(django_user_model):
    def anlegen(name, *rollennamen):
        benutzer = django_user_model.objects.create_user(username=name, password=PASSWORT)
        for rolle in rollennamen:
            benutzer.groups.add(Group.objects.get(name=rolle))
        return benutzer

    return anlegen


@pytest.fixture
def admin(django_user_model):
    benutzer = django_user_model.objects.create_superuser(username="chefin", password=PASSWORT)
    benutzer.groups.add(Group.objects.get(name=rollen.ADMIN))
    return benutzer


def code_fuer(geraet: TOTPDevice) -> str:
    from django_otp.oath import TOTP

    totp = TOTP(geraet.bin_key, geraet.step, geraet.t0, geraet.digits, geraet.drift)
    return f"{totp.token():0{geraet.digits}d}"


@pytest.fixture
def anmelden():
    """Meldet einen Benutzer an, wie es nach erfolgreicher Zwei-Faktor-Anmeldung aussieht."""

    def ausfuehren(client, benutzer, zwei_faktor=True):
        client.force_login(benutzer)
        if zwei_faktor:
            geraet = TOTPDevice.objects.create(user=benutzer, name="Test", confirmed=True)
            sitzung = client.session
            sitzung[DEVICE_ID_SESSION_KEY] = geraet.persistent_id
            sitzung.save()
        return client

    return ausfuehren


@pytest.fixture
def admin_client(client, admin, anmelden):
    return anmelden(client, admin)


@pytest.fixture
def pdf_text(monkeypatch):
    """Erzeugte PDFs unkomprimiert, damit Tests den Text darin finden (WinAnsi = cp1252)."""
    from reportlab import rl_config

    monkeypatch.setattr(rl_config, "pageCompression", 0)

    def lesen(antwort) -> str:
        assert antwort.status_code == 200, antwort.status_code
        assert antwort["Content-Type"] == "application/pdf"
        inhalt = b"".join(antwort.streaming_content) if antwort.streaming else antwort.content
        assert inhalt.startswith(b"%PDF")
        # Umlaute stehen als Oktal-Escapes im Text (z. B. \\344 = ä), Klammern als \\( \\)
        inhalt = re.sub(rb"\\([0-7]{3})", lambda m: bytes([int(m.group(1), 8)]), inhalt)
        inhalt = inhalt.replace(b"\\(", b"(").replace(b"\\)", b")")
        return inhalt.decode("cp1252", errors="replace")

    return lesen


@pytest.fixture
def recht_geben():
    """Gibt einer Rolle zusätzlich Rechte (ADR 0033), z. B. recht_geben("Büro", "x.y")."""
    from apps.konten.models import Rolle

    def geben(rollenname, *codes):
        rolle = Rolle.objects.get(gruppe__name=rollenname)
        rolle.rechte = sorted(set(rolle.rechte) | set(codes))
        rolle.save()

    return geben


@pytest.fixture
def recht_nehmen():
    """Nimmt einer Rolle Rechte, z. B. recht_nehmen("Ausgabe", "einlass.nutzen")."""
    from apps.konten.models import Rolle

    def nehmen(rollenname, *codes):
        rolle = Rolle.objects.get(gruppe__name=rollenname)
        rolle.rechte = [r for r in rolle.rechte if r not in codes]
        rolle.save()

    return nehmen


@pytest.fixture
def gruppe_behalten(db):
    """Kunden ohne gültigen Ausweis bleiben in der Kundengruppe (ADR 0061 abgeschaltet), für
    Tests, die etwas anderes prüfen."""
    from apps.kunden.models import KundenEinstellungen

    e = KundenEinstellungen.laden()
    e.gruppe_behalten = True
    e.save()

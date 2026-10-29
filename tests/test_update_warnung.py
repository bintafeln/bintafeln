"""Warnung auf der Startseite bei wichtigen Updates (ADR 0084)."""

import datetime as dt
import shutil
import subprocess
from pathlib import Path

import pytest
from django.core import mail
from django.urls import reverse
from django.utils import timezone

from apps.core import update
from apps.core.models import TafelEinstellungen

pytestmark = pytest.mark.django_db
START = reverse("core:start")


def _zeit(t):
    return timezone.localtime(t).strftime("%Y-%m-%dT%H:%M:%S%z")


def _tag(tage: int) -> str:
    return (timezone.localdate() - dt.timedelta(days=tage)).isoformat()


@pytest.fixture
def ordner(settings, tmp_path):
    settings.BETRIEB_ORDNER = tmp_path
    (tmp_path / "lebenszeichen.txt").write_text(f"zeit={_zeit(timezone.now())}\n")
    return tmp_path


def versionen(ordner, *zeilen, erfolgreich_vor_tagen=0):
    erfolgreich = _zeit(timezone.now() - dt.timedelta(days=erfolgreich_vor_tagen))
    (ordner / "versionen.txt").write_text(
        f"abgerufen={_zeit(timezone.now())}\nerfolgreich={erfolgreich}\ninstalliert=2026.10.2\n"
        f"fehler=\nversion=2026.10.2|{_tag(60)}|Installiert\t\n" + "".join(z + "\n" for z in zeilen)
    )


def test_stufen_und_hinweise_lesen(ordner):
    versionen(ordner, f"version=2026.10.3|{_tag(3)}|Neu\t", "stufe=2026.10.3|neu",
              "stufe=2026.10.2|quatsch", "sicherheit=2026.10.3|Lücke im Formular",
              "sicherheit=2026.9.1|Alte Lücke", "sicherheit=kaputt|x")  # fmt: skip
    s = update.stand()
    assert [(v.name, v.stufe) for v in s.versionen] == [("2026.10.3", "neu"),
                                                        ("2026.10.2", "klein")]  # fmt: skip
    assert s.versionen[0].stufe_text == "Neue Funktionen" and s.erfolgreich
    assert [h.version for h in s.offene_hinweise()] == ["2026.10.3"]


@pytest.mark.parametrize(
    ("zeilen", "erwartet"),
    [
        ([], None),  # aktuell
        ([f"version=2026.10.3|{_tag(400)}|x\t"], None),  # nur Kleines, auch nach langer Zeit
        ([f"version=2026.10.3|{_tag(0)}|x\t", "stufe=2026.10.3|sicherheit"], ("sicherheit", 0)),
        ([f"version=2026.10.3|{_tag(6)}|x\t", "stufe=2026.10.3|wichtig"], None),
        ([f"version=2026.10.3|{_tag(7)}|x\t", "stufe=2026.10.3|wichtig"], ("wichtig", 7)),
        ([f"version=2026.10.3|{_tag(29)}|x\t", "stufe=2026.10.3|neu"], None),
        (
            [
                f"version=2026.10.3|{_tag(31)}|x\t",
                "stufe=2026.10.3|neu",
                f"version=2026.10.4|{_tag(1)}|y\t",
            ],
            ("neu", 31),
        ),  # fmt: skip
        ([f"version=2026.10.3|{_tag(2)}|x\t", "sicherheit=2026.10.3|Lücke"], ("sicherheit", 2)),
        (["sicherheit=2026.10.2|Schon behoben"], None),
    ],
)
def test_warnregeln(ordner, zeilen, erwartet):
    versionen(ordner, *zeilen)
    w = update.warnung(update.stand())
    assert (w.art, w.tage) == erwartet if erwartet else w is None


def test_warnung_abruf_und_ohne_installierte_version(ordner):
    versionen(ordner, erfolgreich_vor_tagen=15)
    assert update.warnung(update.stand()).art == "abruf"
    versionen(ordner, f"version=2026.10.3|{_tag(0)}|x\t", "stufe=2026.10.3|sicherheit",
              erfolgreich_vor_tagen=15)  # fmt: skip
    assert update.warnung(update.stand()).art == "sicherheit"  # Sicherheit geht vor
    (ordner / "versionen.txt").write_text("installiert=\n")
    assert update.warnung(update.stand()) is None  # Entwicklung ohne Version


def test_startseite_nur_mit_update_recht(client, admin_client, ordner, benutzer_mit_rolle,
                                         anmelden, recht_geben):  # fmt: skip
    versionen(ordner, f"version=2026.10.3|{_tag(4)}|x\t", "stufe=2026.10.3|sicherheit",
              "sicherheit=2026.10.3|Lücke im Formular")  # fmt: skip
    seite = admin_client.get(START).content.decode()
    assert "Sicherheitsupdate verfügbar: Version 2026.10.3" in seite
    assert "seit 4 Tagen" in seite and "Lücke im Formular" in seite
    einlass = benutzer_mit_rolle("einlass", "Ausgabe")
    anmelden(client, einlass)
    assert "Sicherheitsupdate" not in client.get(START).content.decode()
    recht_geben("Ausgabe", "system.update")
    assert "Sicherheitsupdate" in client.get(START).content.decode()


def test_neue_funktionen_spaeter_erinnern(admin_client, ordner):
    versionen(ordner, f"version=2026.10.3|{_tag(40)}|x\t", "stufe=2026.10.3|neu")
    assert "Neue Funktionen verfügbar" in admin_client.get(START).content.decode()
    admin_client.post(reverse("core:update_spaeter"))
    bis = TafelEinstellungen.laden().update_hinweis_bis
    assert bis == timezone.localdate() + dt.timedelta(days=30)
    assert "Neue Funktionen" not in admin_client.get(START).content.decode()
    # eine Sicherheitswarnung lässt sich nicht ausblenden
    versionen(ordner, f"version=2026.10.3|{_tag(40)}|x\t", "stufe=2026.10.3|sicherheit")
    assert "Sicherheitsupdate" in admin_client.get(START).content.decode()


def test_wichtig_und_abruf_auf_der_startseite(admin_client, ordner):
    versionen(ordner, f"version=2026.10.3|{_tag(9)}|x\t", "stufe=2026.10.3|wichtig")
    assert "Wichtige Korrektur verfügbar" in admin_client.get(START).content.decode()
    versionen(ordner, erfolgreich_vor_tagen=20)
    assert "Seit 20 Tagen konnte bintafeln" in admin_client.get(START).content.decode()


def test_mail_einmal_je_sicherheitsupdate(admin_client, admin, ordner, benutzer_mit_rolle,
                                         monkeypatch):  # fmt: skip
    gesendet = []
    monkeypatch.setattr("apps.core.mail.senden", lambda betreff, text, an: gesendet.append(
        (betreff, text, an)))  # fmt: skip
    admin.email = "chefin@example.org"
    admin.save()
    einlass = benutzer_mit_rolle("einlass", "Ausgabe")
    einlass.email = "einlass@example.org"  # ohne Update-Recht: keine Mail
    einlass.save()
    versionen(ordner, f"version=2026.10.3|{_tag(0)}|x\t", "stufe=2026.10.3|sicherheit",
              "sicherheit=2026.10.3|Lücke im Formular")  # fmt: skip
    admin_client.get(START)
    admin_client.get(START)
    assert len(gesendet) == 1
    betreff, text, an = gesendet[0]
    assert an == ["chefin@example.org"] and "Version 2026.10.3" in text
    assert "Lücke im Formular (behoben ab 2026.10.3)" in text
    versionen(ordner, f"version=2026.10.5|{_tag(0)}|x\t", "stufe=2026.10.5|sicherheit")
    admin_client.get(START)
    assert len(gesendet) == 2  # neues Sicherheitsupdate, neue Mail
    assert not mail.outbox


def test_mailfehler_bricht_nichts(admin_client, admin, ordner):
    admin.email = "chefin@example.org"
    admin.save()
    versionen(ordner, f"version=2026.10.3|{_tag(0)}|x\t", "stufe=2026.10.3|sicherheit")
    assert admin_client.get(START).status_code == 200  # ohne Mailserver: nur ein Logeintrag
    assert TafelEinstellungen.laden().update_gemeldet == "2026.10.3"


def test_update_seite_zeigt_stufe_und_hinweis(admin_client, ordner):
    versionen(ordner, f"version=2026.10.3|{_tag(0)}|x\t", "stufe=2026.10.3|sicherheit",
              "sicherheit=2026.10.3|Lücke im Formular")  # fmt: skip
    seite = admin_client.get(reverse("core:update")).content.decode()
    assert '<span class="stufe stufe-sicherheit">Sicherheitsupdate</span>' in seite
    assert "Die installierte Version ist betroffen" in seite and "Lücke im Formular" in seite


def test_dienst_liest_stufe_und_sicherheitshinweise(tmp_path):
    git_pfad, sh_pfad = shutil.which("git"), shutil.which("sh")
    if not git_pfad or not sh_pfad:
        pytest.skip("git oder sh fehlt")
    skript = Path("docker/updater/updater.sh").read_text(encoding="utf-8")
    teile = [skript[skript.index(f"{n}() {{") :] for n in ("stufe", "sicherheitshinweise")]
    funktionen = "\n".join(t[: t.index("\n}\n") + 3] for t in teile)
    quelle, projekt = tmp_path / "quelle", tmp_path / "projekt"
    quelle.mkdir()

    def git(*a, cwd=quelle):
        subprocess.run([git_pfad, "-c", "user.name=Test", "-c", "user.email=t@example.org", *a],  # noqa: S603 – feste Testbefehle
                       cwd=cwd, check=True, capture_output=True)  # fmt: skip

    git("init", "-q", "-b", "main")
    (quelle / "docs").mkdir()
    (quelle / "docs" / "sicherheitshinweise.txt").write_text(
        "# Kommentar\n2026.11.2 Lücke im | Formular\nkaputt x\n", encoding="utf-8")  # fmt: skip
    git("add", ".")
    git("commit", "-q", "-m", "Anfang")
    git("tag", "2026.11.1")
    git("tag", "-a", "2026.11.2", "-m", "2026.11.2", "-m", "stufe=sicherheit")
    git("clone", "-q", str(quelle), str(projekt), cwd=tmp_path)
    ergebnis = subprocess.run(  # noqa: S603 – Funktionen aus dem eigenen Skript
        [sh_pfad, "-c", f"PROJEKT={projekt}\n{funktionen}\n"
         "echo \"[$(stufe 2026.11.1)][$(stufe 2026.11.2)]\"\nsicherheitshinweise"],
        check=True, capture_output=True, text=True,
    ).stdout  # fmt: skip
    assert ergebnis.splitlines() == ["[][sicherheit]",
                                     "sicherheit=2026.11.2|Lücke im / Formular"]  # fmt: skip

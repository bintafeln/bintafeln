"""Dienst „abruf“ (ADR 0127) gegen eine nachgebaute Seite: Anmeldung, 2FA-Code, Spenderliste,
vorhandener und neu erzeugter Finanzexport. Die Seite ahmt nur die Felder und Knöpfe nach, die
der Dienst benutzt; alle Daten sind erfunden."""

import importlib.util
import io
import json
import os
import threading
import time
import urllib.error
import urllib.request
import zipfile
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, urlparse

import pytest

PFAD = Path(__file__).resolve().parents[2] / "docker" / "abruf" / "abruf.py"
SCHLUESSEL = "nur-ein-erfundener-test-schluessel"
KURZ = {"zeile": 2, "knopf": 1, "felder": 2, "zwei_faktor": 2, "code": 20, "nach_anmeldung": 0.2,
        "nach_code": 0.5, "liste_laden": 0.5, "export_laden": 0.5, "klick": 0.1, "abfangen": 3,
        "erzeugen": 20, "download": 20}  # fmt: skip


def _zip(mit_spalten=True) -> bytes:
    """Ein erfundener Export; mit Übersicht, in der die Spalten zum Versand stehen, oder ohne."""
    from openpyxl import Workbook

    mappe, excel = Workbook(), io.BytesIO()
    mappe.active.append(["Belegnummer", "Versendet am"] if mit_spalten else ["Belegnummer"])
    mappe.save(excel)
    puffer = io.BytesIO()
    with zipfile.ZipFile(puffer, "w") as z:
        z.writestr("Spenden/Spendenbeleg_000001.pdf", b"%PDF erfunden")
        z.writestr("Finanzexport.xlsx", excel.getvalue())
    return puffer.getvalue()


def _liste() -> bytes:
    from openpyxl import Workbook

    mappe, puffer = Workbook(), io.BytesIO()
    mappe.active.append(["Vorname", "Nachname", "E-Mail"])
    mappe.active.append(["Erika", "Beispiel", "erika@example.org"])
    mappe.save(puffer)
    return puffer.getvalue()


ANMELDUNG = """<form method="post" action="/login"><input name="eml-user">
<input name="psw-user" type="password"><button type="submit">Anmelden</button></form>"""
ZWEI = """<input name="twoFactorActivate"><button id="ms-two-factor-submit" disabled
 onclick="fetch('/zwei?code='+document.querySelector('input').value).then(()=>location='/start')"
>Weiter</button>"""
LISTE = """<button class="mat-icon-button" disabled>0</button>
<button class="mat-icon-button">1</button><button class="mat-icon-button">2</button>
<button class="mat-icon-button">3</button>
<button class="mat-icon-button" onclick="location='/liste.xlsx'">Export</button>"""
ZEILEN = """<table>
<tr><td><em>(01.01.2026 - 31.01.2026)</em></td><td><button pendo-id="tae-download"
 onclick="fetch('/api/download/falsch.zip')"><span>Herunterladen</span></button></td></tr>
<tr><td><em>(01.02.2026 - 04.02.2026)</em></td><td><button pendo-id="tae-download"
 style="pointer-events: none"><span>Herunterladen</span></button></td></tr>
<tr><td><em>(01.02.2026 - 04.02.2026)</em></td><td>ohne Knopf</td></tr>
%s</table>"""
FERTIG_ALT = """<tr><td><em>(01.02.2026 - 04.02.2026)</em></td><td><button pendo-id="tae-download"
 onclick="fetch('/api/download/alt.zip')"><span>Herunterladen</span></button></td></tr>"""
FERTIG = """<tr><td><em>(01.02.2026 - 04.02.2026)</em></td><td><button pendo-id="tae-download"
 onclick="fetch('/api/download/7.zip')"><span>Herunterladen</span></button></td></tr>"""
# Neuen Export erzeugen: Die Datumsfelder tragen absichtlich andere Nummern als im bisherigen
# Programm (mat-input-7/-8), weil das Vereinsportal sie der Reihe nach vergibt. Nach „Erstellen“
# erscheint oben eine Zeile mit dem Zeitraum, die erst nach kurzer Zeit herunterladbar ist.
NEU = (ZEILEN % "") + """<mat-select style="display:block"
 onclick="document.getElementById('wahl').style.display='block'">Zeitraum</mat-select>
<div id="wahl" style="display:none"><mat-option style="display:block">Dieses Jahr</mat-option>
<mat-option style="display:block" onclick="window.eigen=true">Benutzerdefiniert</mat-option></div>
<input id="suche" placeholder="Suchen">
<input id="mat-input-7" class="mat-datepicker-input">
<input id="mat-input-8" class="mat-datepicker-input">
<div class="mat-expansion-panel-header" onclick="aufklappen()"><span>Erweiterte Einstellungen</span>
<mat-icon>expand_more</mat-icon></div>
<div id="erweitert"></div>
<button onclick="erstellen()">Erstellen</button>
<script>
// Wie im Vereinsportal (Angular Material): Die Spalten gibt es erst, wenn „Erweiterte
// Einstellungen“ aufgeklappt ist – das dauert einen Moment; die Überschrift trägt ein Symbol als
// Text, die Beschriftung steht neben dem Kästchen, nicht darum herum.
function aufklappen() {
  setTimeout(() => document.getElementById('erweitert').innerHTML = ['Status', '+Name',
    '+Versendet am', 'SQ-verschickt', 'SQ-erstellt Datum'].map((n, i) => '<mat-checkbox'
    + ' class="mat-mdc-checkbox"><div class="mdc-form-field"><div class="mdc-checkbox">'
    + '<input type="checkbox" class="mdc-checkbox__native-control" id="k' + i + '"'
    + (n[0] === '+' ? ' checked' : '') + '></div><label for="k' + i + '"> '
    + n.replace('+', '') + ' </label></div></mat-checkbox>').join(''), 150);
}
function erstellen() {
  const v = VON, w = BIS, tr = document.createElement('tr');
  const spalten = [...document.querySelectorAll('#erweitert input:checked')]
    .map(i => i.closest('mat-checkbox').querySelector('label').innerText.trim()).join('|');
  tr.innerHTML = '<td><em>(' + v + ' - ' + w + ')</em></td><td><button pendo-id="tae-download"'
    + ' style="pointer-events: none"><span>Herunterladen</span></button></td>';
  tr.querySelector('button').onclick = () => location = '/neu.zip?von=' + v + '&bis=' + w
    + '&eigen=' + window.eigen + '&spalten=' + encodeURIComponent(spalten);
  document.querySelector('table').prepend(tr);
  setTimeout(() => tr.querySelector('button').removeAttribute('style'), 800);
}</script>"""  # fmt: skip
# … wie es sein soll: Das Vereinsportal nimmt den eingestellten Zeitraum
NEU_RICHTIG = NEU.replace("VON", "document.getElementById('mat-input-7').value").replace(
    "BIS", "document.getElementById('mat-input-8').value"
)
# … und der Fehlerfall: Es erzeugt den Export für einen anderen Zeitraum
NEU_FALSCH = NEU.replace("VON", "'01.01.2025'").replace("BIS", "'31.12.2025'")
# … oder die Felder nehmen die Eingabe nicht an
NEU_STARR = NEU_RICHTIG.replace(
    "<script>",
    "<script>for (const f of document.querySelectorAll('.mat-datepicker-input'))"
    " f.addEventListener('input', () => f.value = '');",
)


# Ein Hinweis, der die ganze Seite überdeckt (wie ein Cookie-Hinweis): Klicks kommen nicht durch
BANNER = '<div id="hinweis" class="cookie banner" style="position:fixed;inset:0;z-index:9">x</div>'
# Anmeldung ohne Knopf vom Typ „submit“: Das Formular muss direkt abgeschickt werden
OHNE_KNOPF = """<form method="post" action="/login"><input name="eml-user">
<input name="psw-user" type="password"><a href="#">Anmelden</a></form>"""


class Portal(BaseHTTPRequestHandler):
    angemeldet = False
    banner = False
    gesehen: dict = {}

    def log_message(self, *args):
        pass

    def _html(self, text: str):
        inhalt = f"<!doctype html><meta charset=utf-8>{text}".encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(inhalt)))
        self.end_headers()
        self.wfile.write(inhalt)

    def _datei(self, inhalt: bytes, art: str, name: str = ""):
        self.send_response(200)
        self.send_header("Content-Type", art)
        if name:
            self.send_header("Content-Disposition", f'attachment; filename="{name}"')
        self.send_header("Content-Length", str(len(inhalt)))
        self.end_headers()
        self.wfile.write(inhalt)

    def do_POST(self):
        daten = parse_qs(self.rfile.read(int(self.headers["Content-Length"])).decode())
        type(self).gesehen["anmeldung"] = (daten["eml-user"][0], daten["psw-user"][0])
        # wie im Vereinsportal: nur mit richtigem Passwort folgt die Abfrage des 2FA-Codes
        zusatz = BANNER if type(self).banner else ""
        self._html((ZWEI if daten["psw-user"][0] == "erfunden" else ANMELDUNG + "Falsch.") + zusatz)

    def do_GET(self):
        teile = urlparse(self.path)
        pfad, frage = teile.path, parse_qs(teile.query)
        if pfad == "/login":
            return self._html(ANMELDUNG + (BANNER if type(self).banner else ""))
        if pfad == "/login-ohne-knopf":
            return self._html(OHNE_KNOPF)
        if pfad == "/zwei":
            type(self).angemeldet = frage.get("code") == ["123456"]
            return self._html("ok")
        if not type(self).angemeldet:
            self.send_response(302)
            self.send_header("Location", "/login")
            return self.end_headers()
        if pfad == "/liste":
            return self._html(LISTE)
        if pfad == "/liste.xlsx":
            return self._datei(_liste(), "application/vnd.ms-excel", "liste.xlsx")
        if pfad == "/export-vorhanden":
            return self._html(ZEILEN % FERTIG)
        if pfad == "/export-neu":
            return self._html(NEU_RICHTIG)
        if pfad == "/export-falsch":
            return self._html(NEU_FALSCH)
        if pfad == "/export-starr":
            return self._html(NEU_STARR)
        if pfad == "/export-ohne-erweitert":  # die Seite hat (noch) keinen Bereich mit Spalten
            return self._html(NEU_RICHTIG.replace("Erweiterte Einstellungen", "Mehr"))
        if pfad == "/export-ohne-spalten":  # fertiger Export, aber ohne Spalten zum Versand
            return self._html(NEU_RICHTIG.replace("</table>", FERTIG_ALT + "</table>", 1))
        if pfad == "/liste-leer":
            return self._html("<button>Hilfe</button><button class='x y'>Menü</button>")
        if pfad == "/api/download/falsch.zip":
            type(self).gesehen["falsch"] = True
            return self._datei(_zip(), "application/zip")
        if pfad == "/api/download/7.zip":
            return self._datei(_zip(), "application/zip")
        if pfad == "/api/download/alt.zip":
            type(self).gesehen["alt"] = True
            return self._datei(_zip(mit_spalten=False), "application/zip")
        if pfad == "/neu.zip":
            type(self).gesehen["spalten"] = frage.pop("spalten", [""])[0].split("|")
            type(self).gesehen["neu"] = {k: v[0] for k, v in frage.items()}
            return self._datei(_zip(), "application/zip", "export.zip")
        return self._html("Startseite")


def _server(klasse):
    server = ThreadingHTTPServer(("127.0.0.1", 0), klasse)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    return server, f"http://127.0.0.1:{server.server_port}"


@pytest.fixture
def dienst(monkeypatch):
    spec = importlib.util.spec_from_file_location("abruf_dienst", PFAD)
    modul = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modul)
    monkeypatch.setattr(modul, "ZEITEN", dict(KURZ))
    monkeypatch.setattr(modul, "NUR_HTTPS", False)
    Portal.angemeldet, Portal.gesehen, Portal.banner = False, {}, False
    portal, portal_url = _server(Portal)

    class Anfrage(modul.Anfrage):
        schluessel = SCHLUESSEL
        auftrag = modul.Auftrag()
        browser_pfad = os.environ.get("BINTAFELN_E2E_CHROMIUM") or None

    server, url = _server(Anfrage)

    def rufen(pfad, daten=None, schluessel=SCHLUESSEL, roh=False):
        anfrage = urllib.request.Request(  # noqa: S310
            url + pfad, data=None if daten is None else json.dumps(daten).encode(),
            headers={"X-Abruf-Schluessel": schluessel}, method="GET" if daten is None else "POST",
        )  # fmt: skip
        try:
            with urllib.request.urlopen(anfrage, timeout=10) as antwort:  # noqa: S310
                inhalt = antwort.read()
                return 200, inhalt if roh else json.loads(inhalt)
        except urllib.error.HTTPError as fehler:
            return fehler.code, json.loads(fehler.read())

    def warten_auf(*staende, sekunden=40):
        ende = time.monotonic() + sekunden
        while time.monotonic() < ende:
            stand = rufen("/stand")[1]
            if stand["stand"] in staende:
                return stand
            time.sleep(0.2)
        raise AssertionError(f"Stand bleibt {stand}")

    def auftrag(export="/export-vorhanden", **mehr):
        return {"anmeldung_url": f"{portal_url}/login", "liste_url": f"{portal_url}/liste",
                "export_url": portal_url + export, "email": "buero@example.org",
                "passwort": "erfunden", "von": "01.02.2026", "bis": "04.02.2026",
                "mit_liste": True} | mehr  # fmt: skip

    yield type("Dienst", (), {"rufen": staticmethod(rufen), "warten_auf": staticmethod(warten_auf),
                              "auftrag": staticmethod(auftrag), "modul": modul, "url": url,
                              "portal": portal_url})  # fmt: skip
    server.shutdown()
    portal.shutdown()


def test_abruf_mit_vorhandenem_export(dienst):
    assert dienst.rufen("/stand", schluessel="falsch")[0] == 403
    assert dienst.rufen("/stand")[1]["stand"] == "frei"
    assert dienst.rufen("/datei/finanzexport")[0] == 404
    assert dienst.rufen("/code", {"code": "123456"})[0] == 400  # es wartet noch niemand
    status, antwort = dienst.rufen("/start", dienst.auftrag())
    assert (status, antwort["stand"], antwort["nummer"]) == (200, "laeuft", 1)
    # ein zweiter Auftrag wird abgewiesen
    assert dienst.rufen("/start", dienst.auftrag())[0] == 409
    assert dienst.warten_auf("warte_auf_code")["schritt"] == "Bitte den 2FA-Code eingeben"
    assert dienst.rufen("/code", {"code": "12"})[0] == 400
    assert dienst.rufen("/code", {"code": "123456"})[1]["stand"] == "laeuft"
    stand = dienst.warten_auf("fertig", "fehler")
    assert stand["stand"] == "fertig", stand
    assert stand["dateien"] == {"spenderliste": True, "finanzexport": True}
    assert Portal.gesehen["anmeldung"] == ("buero@example.org", "erfunden")
    assert dienst.rufen("/datei/spenderliste", roh=True)[1].startswith(b"PK")
    export = dienst.rufen("/datei/finanzexport", roh=True)[1]
    assert zipfile.ZipFile(io.BytesIO(export)).namelist() == [
        "Spenden/Spendenbeleg_000001.pdf", "Finanzexport.xlsx"]  # fmt: skip
    assert "neu" not in Portal.gesehen  # der vorhandene Export wurde wiederverwendet
    assert dienst.rufen("/fertig", {})[1]["stand"] == "frei"
    assert dienst.rufen("/datei/finanzexport")[0] == 404
    assert dienst.rufen("/unbekannt", {})[0] == 404


def test_abruf_erzeugt_neuen_export_ohne_spenderliste(dienst):
    dienst.rufen("/start", dienst.auftrag("/export-neu", mit_liste=False, liste_url=""))
    dienst.warten_auf("warte_auf_code")
    dienst.rufen("/code", {"code": "123456"})
    stand = dienst.warten_auf("fertig", "fehler")
    assert stand["stand"] == "fertig", stand
    assert stand["dateien"] == {"spenderliste": False, "finanzexport": True}
    assert Portal.gesehen["neu"] == {"von": "01.02.2026", "bis": "04.02.2026", "eigen": "true"}
    # nicht irgendein fertiger Export der Seite, sondern genau der für den Zeitraum
    assert "falsch" not in Portal.gesehen
    assert stand["hinweise"] == []
    # die Spalten zum Versand sind angekreuzt, alles andere ist geblieben, wie es war
    assert Portal.gesehen["spalten"] == ["Name", "Versendet am", "SQ-verschickt",
                                         "SQ-erstellt Datum"]  # fmt: skip


def test_vorhandener_export_ohne_spalten_wird_neu_erzeugt(dienst):
    """Einem schon vorhandenen Export fehlen die Spalten zum Versand: Er wird nicht benutzt,
    sondern mit den Spalten neu erzeugt."""
    dienst.rufen("/start", dienst.auftrag("/export-ohne-spalten", mit_liste=False))
    dienst.warten_auf("warte_auf_code")
    dienst.rufen("/code", {"code": "123456"})
    stand = dienst.warten_auf("fertig", "fehler")
    assert stand["stand"] == "fertig", stand
    assert Portal.gesehen["alt"] and Portal.gesehen["neu"]["von"] == "01.02.2026"
    assert "SQ-erstellt Datum" in Portal.gesehen["spalten"]
    export = dienst.rufen("/datei/finanzexport", roh=True)[1]
    assert dienst.modul.mit_versand(io.BytesIO(export))
    assert not dienst.modul.mit_versand(io.BytesIO(_zip(mit_spalten=False)))


def test_anderer_zeitraum_laedt_einen_anderen_export(dienst):
    """Der Fehler vom ersten echten Lauf: Wer den Zeitraum ändert, muss auch den Export für
    diesen Zeitraum bekommen."""
    auftrag = dienst.auftrag("/export-neu", mit_liste=False, von="05.03.2026", bis="20.03.2026")
    dienst.rufen("/start", auftrag)
    dienst.warten_auf("warte_auf_code")
    dienst.rufen("/code", {"code": "123456"})
    stand = dienst.warten_auf("fertig", "fehler")
    assert stand["stand"] == "fertig", stand
    assert Portal.gesehen["neu"] == {"von": "05.03.2026", "bis": "20.03.2026", "eigen": "true"}


def test_portal_erzeugt_einen_anderen_zeitraum(dienst):
    """Übernimmt das Vereinsportal den Zeitraum nicht, bricht der Abruf mit einer Erklärung ab,
    statt den falschen Export einzulesen."""
    dienst.rufen("/start", dienst.auftrag("/export-falsch", mit_liste=False))
    dienst.warten_auf("warte_auf_code")
    dienst.rufen("/code", {"code": "123456"})
    stand = dienst.warten_auf("fertig", "fehler")
    assert stand["stand"] == "fehler", stand
    assert "anderen Zeitraum angelegt (01.01.2025 - 31.12.2025)" in stand["fehler"]
    assert "statt 01.02.2026 bis 04.02.2026" in stand["fehler"]
    assert "neu" not in Portal.gesehen and stand["dateien"]["finanzexport"] is False


def test_datumsfelder_nehmen_die_eingabe_nicht_an(dienst):
    dienst.rufen("/start", dienst.auftrag("/export-starr", mit_liste=False))
    dienst.warten_auf("warte_auf_code")
    dienst.rufen("/code", {"code": "123456"})
    stand = dienst.warten_auf("fertig", "fehler")
    assert stand["stand"] == "fehler", stand
    assert "Der Zeitraum ließ sich nicht einstellen" in stand["fehler"]
    assert "statt 01.02.2026 bis 04.02.2026" in stand["fehler"]


def test_spenderliste_ohne_export_knopf_wird_gemeldet(dienst, capsys):
    """Fehlt der Knopf auf der Seite der Liste, läuft der Finanzexport weiter; bintafeln erfährt,
    dass die Liste fehlt, und das Protokoll nennt, welche Knöpfe die Seite hat."""
    auftrag = dienst.auftrag()
    auftrag["liste_url"] = auftrag["liste_url"].replace("/liste", "/liste-leer")
    dienst.rufen("/start", auftrag)
    dienst.warten_auf("warte_auf_code")
    dienst.rufen("/code", {"code": "123456"})
    stand = dienst.warten_auf("fertig", "fehler")
    assert stand["stand"] == "fertig", stand
    assert stand["dateien"] == {"spenderliste": False, "finanzexport": True}
    assert len(stand["hinweise"]) == 1 and "wurde nicht geholt" in stand["hinweise"][0]
    protokoll = capsys.readouterr().out
    assert "Spenderliste: 0 passende Knöpfe" in protokoll and "2 Knöpfe; - | x.y" in protokoll


def test_falscher_code_meldet_fehler_und_neuer_auftrag_geht(dienst):
    dienst.rufen("/start", dienst.auftrag())
    dienst.warten_auf("warte_auf_code")
    dienst.rufen("/code", {"code": "999999"})
    stand = dienst.warten_auf("fertig", "fehler")
    assert stand["stand"] == "fehler" and "Anmeldung hat nicht geklappt" in stand["fehler"]
    assert "(Seite: http://127.0.0.1" in stand["fehler"] and "/login)" in stand["fehler"]
    assert dienst.rufen("/start", dienst.auftrag())[1]["nummer"] == 2
    dienst.warten_auf("warte_auf_code")
    dienst.rufen("/abbrechen", {})
    stand = dienst.warten_auf("fehler")
    assert stand["fehler"] == "Der Abruf wurde abgebrochen."


def test_anmeldung_trotz_hinweis_ueber_der_seite(dienst, capsys):
    """Ein Hinweis über der ganzen Seite (z. B. zu Cookies) verdeckt Knopf und Code-Feld: Der
    Abruf kommt trotzdem durch und schreibt ins Protokoll, was über dem Knopf lag."""
    Portal.banner = True
    dienst.rufen("/start", dienst.auftrag(mit_liste=False))
    dienst.warten_auf("warte_auf_code", "fehler")
    dienst.rufen("/code", {"code": "123456"})
    stand = dienst.warten_auf("fertig", "fehler")
    assert stand["stand"] == "fertig", stand
    protokoll = capsys.readouterr().out
    assert "Anmelde-Knopf nicht anklickbar" in protokoll
    assert "darüber liegt: DIV#hinweis.cookie.banner" in protokoll
    assert "erfunden" not in protokoll and "123456" not in protokoll  # nie Zugangsdaten


def test_anmeldung_ohne_passenden_knopf(dienst, capsys):
    auftrag = dienst.auftrag(mit_liste=False)
    auftrag["anmeldung_url"] = auftrag["anmeldung_url"].replace("/login", "/login-ohne-knopf")
    dienst.rufen("/start", auftrag)
    assert dienst.warten_auf("warte_auf_code", "fehler")["stand"] == "warte_auf_code"
    assert "Kein Anmelde-Knopf gefunden" in capsys.readouterr().out


def test_falsches_passwort_fragt_gar_nicht_erst_nach_dem_code(dienst):
    """Nimmt das Vereinsportal die Anmeldung nicht an, kommt sofort eine Erklärung – statt
    fünf Minuten auf einen Code zu warten, den niemand verschickt hat."""
    dienst.rufen("/start", dienst.auftrag(passwort="falsch"))
    stand = dienst.warten_auf("warte_auf_code", "fehler", "fertig")
    assert stand["stand"] == "fehler", stand
    assert "nicht nach dem 2FA-Code gefragt" in stand["fehler"]
    assert "Stimmen E-Mail und Passwort" in stand["fehler"] and "/login)" in stand["fehler"]


def test_falsche_adresse_der_anmeldeseite(dienst):
    auftrag = dienst.auftrag()
    auftrag["anmeldung_url"] = auftrag["anmeldung_url"].replace("/login", "/zwei?nummer=7")
    dienst.rufen("/start", auftrag)
    stand = dienst.warten_auf("warte_auf_code", "fehler", "fertig")
    assert stand["stand"] == "fehler", stand
    # was hinter dem Fragezeichen steht, zeigt die Meldung nicht – aber dass da etwas stand
    assert "/zwei?…)" in stand["fehler"] and "nummer" not in stand["fehler"]
    assert "Felder für E-Mail und Passwort nicht gefunden" in stand["fehler"]
    assert "Adresse der Anmeldeseite" in stand["fehler"]


def test_unerwartete_seite_nennt_schritt_und_seite(dienst):
    """Sieht eine Seite anders aus als erwartet, steht in der Meldung, bei welchem Schritt."""
    auftrag = dienst.auftrag("/liste")  # die Seite hat weder einen Export noch „Erstellen“
    dienst.rufen("/start", auftrag)
    dienst.warten_auf("warte_auf_code")
    dienst.rufen("/code", {"code": "123456"})
    stand = dienst.warten_auf("fehler", "fertig")
    assert stand["stand"] == "fehler", stand
    schritt = "Beim Schritt „(2/2) Stelle den Zeitraum ein: 01.02.2026 bis 04.02.2026 …“"
    assert schritt in stand["fehler"]
    assert "/liste)" in stand["fehler"]


def test_ohne_code_laeuft_die_zeit_ab(dienst):
    dienst.modul.ZEITEN["code"] = 1
    dienst.rufen("/start", dienst.auftrag())
    assert "kein 2FA-Code" in dienst.warten_auf("fehler")["fehler"]


def test_auftrag_wird_geprueft(dienst):
    antwort = dienst.rufen("/start", dienst.auftrag(passwort="", liste_url=""))
    assert antwort == (409, antwort[1]) and "passwort, liste_url" in antwort[1]["fehler"]
    dienst.modul.NUR_HTTPS = True
    assert "https://" in dienst.rufen("/start", dienst.auftrag())[1]["fehler"]
    assert dienst.rufen("/stand")[1]["stand"] == "frei"


def test_dienst_startet_nicht_ohne_schluessel(dienst, monkeypatch):
    monkeypatch.setenv("ABRUF_SCHLUESSEL", "zu kurz")
    with pytest.raises(SystemExit, match="BINTAFELN_ABRUF_SCHLUESSEL"):
        dienst.modul.main()


def test_abruf_von_der_seite_bis_zum_einlesen(dienst, angemeldet, admin, settings):
    """Die ganze Kette im Browser: Seite in bintafeln → Dienst → nachgebaute Portal-Seite."""
    from django.urls import reverse
    from playwright.sync_api import expect

    from apps.core import geheimnis
    from apps.core.models import TafelEinstellungen
    from apps.vereinsportal.models import Abruf, Kontakt, PortalEinstellungen, Zugang

    t = TafelEinstellungen.laden()
    t.module = ["vereinsportal"]
    t.save()
    settings.ABRUF_URL, settings.ABRUF_SCHLUESSEL = dienst.url, SCHLUESSEL
    e = PortalEinstellungen.laden()
    e.anmeldung_url, e.liste_url = f"{dienst.portal}/login", f"{dienst.portal}/liste"
    e.export_url = f"{dienst.portal}/export-vorhanden"
    e.save()
    Zugang.objects.create(
        benutzer=admin, email="buero@example.org",
        passwort_verschluesselt=geheimnis.verschluesseln("erfunden"),
    )  # fmt: skip
    seite = angemeldet(admin)
    seite.goto(reverse("vereinsportal:abruf"))
    seite.fill("input[name=von]", "01.02.2026")
    seite.fill("input[name=bis]", "04.02.2026")
    seite.locator("#abruf-form button[type=submit]").click()
    # der Stand lädt sich selbst nach, bis nach dem 2FA-Code gefragt wird
    code = seite.locator("#abruf-code")
    expect(code).to_be_visible(timeout=30_000)
    code.fill("123456")
    seite.locator("#abruf-stand button", has_text="Code senden").click()
    stand = seite.locator("#abruf-stand")
    expect(stand).to_contain_text("Spenderliste ersetzt: 1 Spender mit E-Mail.", timeout=40_000)
    # der nachgebaute Export enthält nur einen unlesbaren Beleg: das ist kein Erfolg
    expect(stand).to_contain_text("Kein Beleg ließ sich lesen (1 in der Datei)")
    expect(stand).to_contain_text("Es läuft kein Abruf")
    assert Kontakt.objects.get().email == "erika@example.org"
    # der Abruf steht in der Historie
    expect(seite.locator("#abruf-historie")).to_contain_text("01.02.2026 – 04.02.2026")
    assert Abruf.objects.get().stand == "fehler"


def test_spalten_nicht_gefunden_gibt_einen_hinweis(dienst):
    """Findet der Dienst die Kästchen nicht, läuft der Abruf trotzdem durch und sagt, was er auf
    der Seite gesehen hat – damit sich das Ankreuzen an eine geänderte Seite anpassen lässt."""
    dienst.rufen("/start", dienst.auftrag("/export-ohne-erweitert", mit_liste=False))
    dienst.warten_auf("warte_auf_code")
    dienst.rufen("/code", {"code": "123456"})
    stand = dienst.warten_auf("fertig", "fehler")
    assert stand["stand"] == "fertig", stand
    (hinweis,) = stand["hinweise"]
    assert "„Versendet am“, „SQ-verschickt“, „SQ-erstellt Datum“ nicht ankreuzen" in hinweis
    assert "Auf der Seite wurde kein Kästchen gefunden." in hinweis
    assert "„Erweiterte Einstellungen“ wurde nicht gefunden." in hinweis
    assert Portal.gesehen["spalten"] == [""]

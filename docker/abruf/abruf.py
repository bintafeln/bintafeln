"""Dienst „abruf“: holt Finanzexport und Spenderliste aus dem Vereinsportal (ADR 0127).

bintafeln selbst hat keinen Browser. Dieser kleine Dienst läuft nur bei Tafeln, die ihn
einschalten (Compose-Profil ``abruf``), ist von außen nicht erreichbar und nimmt Aufträge nur mit
dem gemeinsamen Schlüssel an. Er meldet sich im Vereinsportal an, wartet auf den 2FA-Code,
lädt die Dateien herunter und hält sie bereit, bis bintafeln sie abgeholt hat. Zugangsdaten und
Dateien liegen nur im Arbeitsspeicher bzw. in einem vorübergehenden Ordner.

Der Ablauf (Schritte, Felder und Knöpfe der Seiten) stammt aus dem bisherigen
Spendenbelege-Programm der Tafel. Ändert das Vereinsportal seine Seiten, muss ``ablauf()``
angepasst werden; das Hochladen von Hand in bintafeln geht immer.
"""

import hmac
import json
import os
import shutil
import tempfile
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 8700
NUR_HTTPS = True  # Tests gegen eine nachgebaute Seite schalten das ab
DATEIEN = {"spenderliste": "spenderliste.xlsx", "finanzexport": "finanzexport.zip"}

# Wartezeiten in Sekunden; Tests setzen sie herunter
ZEITEN = {
    "code": 300,  # so lange wartet der Dienst auf den 2FA-Code
    "felder": 15,  # so lange dürfen die Felder der Anmeldeseite auf sich warten lassen
    "zwei_faktor": 30,  # … und die Abfrage des 2FA-Codes nach dem Absenden
    "nach_anmeldung": 3,
    "nach_code": 4,
    "liste_laden": 20,
    "export_laden": 5,
    "klick": 1,
    "abfangen": 30,  # Antwort mit der Download-Adresse
    "erzeugen": 4 * 3600,  # ein neuer Export kann lange brauchen
    "download": 600,
}


class Abbruch(Exception):
    """Vom Menschen abgebrochen."""


class Hinweis(RuntimeError):
    """Störung mit einer Erklärung, was der Mensch prüfen kann."""


class Auftrag:
    """Der eine laufende Auftrag; alles nur im Arbeitsspeicher."""

    def __init__(self):
        self.sperre = threading.Lock()
        self.ordner: Path | None = None
        self.leeren()

    def leeren(self):
        if self.ordner:
            shutil.rmtree(self.ordner, ignore_errors=True)
        self.ordner = None
        self.stand, self.schritt, self.fehler = "frei", "", ""
        self.code, self.abbrechen, self.nummer = "", False, 0

    def melden(self, schritt: str, stand: str | None = None):
        print(f"[abruf] {schritt}", flush=True)  # für „docker compose logs abruf“; nie Zugangsdaten
        self.schritt = schritt
        if stand:
            self.stand = stand

    def pruefen(self):
        if self.abbrechen:
            raise Abbruch

    def datei(self, art: str) -> Path:
        return self.ordner / DATEIEN[art]

    def als_json(self) -> dict:
        vorhanden = {a: bool(self.ordner and self.datei(a).exists()) for a in DATEIEN}
        return {"stand": self.stand, "schritt": self.schritt, "fehler": self.fehler,
                "dateien": vorhanden, "nummer": self.nummer}  # fmt: skip


AUFTRAG = Auftrag()


def _warten(auftrag: Auftrag, seite, sekunden: float):
    """Wartet in kleinen Schritten, damit ein Abbruch schnell greift."""
    ende = time.monotonic() + sekunden
    while time.monotonic() < ende:
        auftrag.pruefen()
        seite.wait_for_timeout(min(500, max(1, (ende - time.monotonic()) * 1000)))


def _da(seite, auswahl: str, sekunden: float) -> bool:
    """Erscheint das Element rechtzeitig auf der Seite?"""
    try:
        seite.wait_for_selector(auswahl, timeout=sekunden * 1000)
    except Exception:  # noqa: BLE001 – Zeitüberschreitung oder Seite weg: beides heißt „nein“
        return False
    return True


def _beschreiben(auftrag: Auftrag, seite, fehler: Exception) -> str:
    """Die Störung so, dass man sie weitergeben kann: Schritt, Ursache und Seite (ohne das, was
    hinter dem Fragezeichen steht)."""
    text = str(fehler).splitlines()[0] if str(fehler) else type(fehler).__name__
    if not isinstance(fehler, Hinweis):
        if "Timeout" in text:
            text = f"Die Seite sah anders aus als erwartet oder antwortete zu langsam ({text})"
        text = f"Beim Schritt „{auftrag.schritt}“: {text}"
    try:
        ort = seite.url.split("?")[0]
    except Exception:  # noqa: BLE001 – der Browser kann schon weg sein
        ort = ""
    return f"{text} (Seite: {ort})"[:500] if ort else text[:500]


def _anmelden(auftrag: Auftrag, seite, d: dict):
    auftrag.melden("Öffne die Anmeldeseite …")
    seite.goto(d["anmeldung_url"], timeout=30000)
    if not _da(seite, 'input[name="eml-user"]', ZEITEN["felder"]):
        raise Hinweis(
            "Auf der Anmeldeseite wurden die Felder für E-Mail und Passwort nicht gefunden. "
            "Stimmt die „Adresse der Anmeldeseite“ in den Einstellungen?"
        )
    auftrag.melden("Gebe die Zugangsdaten ein …")
    seite.fill('input[name="eml-user"]', d["email"])
    seite.fill('input[name="psw-user"]', d["passwort"])
    seite.locator(
        'form:has(input[name="eml-user"]) input[type="submit"], '
        'form:has(input[name="eml-user"]) button[type="submit"]'
    ).first.click()
    seite.wait_for_load_state("domcontentloaded", timeout=15000)
    _warten(auftrag, seite, ZEITEN["nach_anmeldung"])
    # Erst nach dem Code fragen, wenn das Vereinsportal ihn wirklich haben will. Sonst wartet
    # der Mensch fünf Minuten auf einen Code, den das Portal nie verschickt hat.
    auftrag.melden("Warte auf die Abfrage des 2FA-Codes …")
    if not _da(seite, 'input[name="twoFactorActivate"]', ZEITEN["zwei_faktor"]):
        raise Hinweis(
            "Nach dem Absenden von E-Mail und Passwort hat das Vereinsportal nicht nach dem "
            "2FA-Code gefragt. Stimmen E-Mail und Passwort in den Einstellungen?"
        )

    auftrag.melden("Bitte den 2FA-Code eingeben", "warte_auf_code")
    ende = time.monotonic() + ZEITEN["code"]
    while not auftrag.code:
        auftrag.pruefen()
        if time.monotonic() > ende:
            raise RuntimeError("Es wurde kein 2FA-Code eingegeben.")
        time.sleep(0.2)
    auftrag.melden("Der 2FA-Code wird eingetragen …", "laeuft")
    # Ziffern einzeln tippen, damit die Seite den Knopf freigibt
    seite.click('input[name="twoFactorActivate"]')
    seite.type('input[name="twoFactorActivate"]', auftrag.code, delay=150)
    _warten(auftrag, seite, ZEITEN["klick"] * 2)
    seite.evaluate("document.getElementById('ms-two-factor-submit').removeAttribute('disabled')")
    seite.evaluate("document.getElementById('ms-two-factor-submit').click()")
    _warten(auftrag, seite, ZEITEN["nach_code"])


def _spenderliste(auftrag: Auftrag, seite, d: dict):
    auftrag.melden("(1/2) Öffne die Spenderliste …")
    seite.goto(d["liste_url"], wait_until="domcontentloaded", timeout=30000)
    _warten(auftrag, seite, ZEITEN["liste_laden"])
    if "login" in seite.url:
        raise Hinweis("Die Anmeldung hat nicht geklappt. War der 2FA-Code richtig?")
    knoepfe = seite.query_selector_all("button.mat-icon-button:not(.disabled):not([disabled])")
    if len(knoepfe) <= 3:
        auftrag.melden(
            f"(1/2) Export-Knopf der Spenderliste nicht gefunden ({len(knoepfe)} Knöpfe)"
        )
        return
    with seite.expect_download(timeout=60000) as geladen:
        knoepfe[3].click()
    geladen.value.save_as(str(auftrag.datei("spenderliste")))
    auftrag.melden("(1/2) Spenderliste gespeichert")
    _warten(auftrag, seite, ZEITEN["klick"] * 3)


def _fertige_exporte(seite, von: str, bis: str) -> list:
    """Knöpfe „Herunterladen“ in den Zeilen, deren Zeitraum passt und die fertig erzeugt sind."""
    knoepfe = []
    for zeile in seite.query_selector_all("table tr"):
        zeitraum = zeile.query_selector("em")
        text = (zeitraum.inner_text() or "") if zeitraum else ""
        if von not in text or bis not in text:
            continue
        knopf = zeile.query_selector('button[pendo-id="tae-download"]')
        if not knopf or "pointer-events: none" in (knopf.get_attribute("style") or ""):
            continue  # fehlt oder wird noch erzeugt
        beschriftung = knopf.query_selector("span")
        if beschriftung and "herunterladen" in (beschriftung.inner_text() or "").lower():
            knoepfe.append(knopf)
    return knoepfe


def _vorhandenen_laden(auftrag: Auftrag, kontext, seite, knopf, ziel: Path) -> bool:
    """Die Seite lädt die Datei über eine Anfrage im Hintergrund: Adresse abfangen und mit der
    Sitzung des Browsers holen; sonst auf einen gewöhnlichen Download hoffen."""
    adresse = []

    def antwort(a):
        art = a.headers.get("content-type", "")
        url = a.url.lower()
        passt = any(w in url for w in ("download", "export", "zip"))
        if (
            not adresse
            and passt
            and a.status in (200, 302)
            and ("zip" in art or "octet" in art or "zip" in url)
        ):
            adresse.append(a.url)

    seite.on("response", antwort)
    try:
        knopf.scroll_into_view_if_needed(timeout=5000)
        knopf.evaluate("el => el.click()")
        ende = time.monotonic() + ZEITEN["abfangen"]
        while not adresse and time.monotonic() < ende:
            _warten(auftrag, seite, 0.5)
    finally:
        seite.remove_listener("response", antwort)
    if adresse:
        geholt = kontext.request.get(adresse[0], timeout=300000)
        if geholt.ok:
            ziel.write_bytes(geholt.body())
            return True
    try:
        with seite.expect_download(timeout=ZEITEN["abfangen"] * 1000) as geladen:
            knopf.evaluate("el => el.click()")
        geladen.value.save_as(str(ziel))
        return True
    except Exception:  # noqa: BLE001 – dann wird der Export neu erzeugt
        return False


FELD_SETZEN = """([id, wert]) => {
    const feld = document.getElementById(id);
    if (!feld) return;
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
        .call(feld, wert);
    for (const art of ['input', 'change', 'blur'])
        feld.dispatchEvent(new Event(art, {bubbles: true}));
}"""
ZAHL_FERTIG = """() => [...document.querySelectorAll('button')].filter(
    b => b.textContent.toLowerCase().includes('herunterladen') && !b.disabled).length"""
ERSTEN_KLICKEN = """() => { const b = [...document.querySelectorAll('button')].find(
    b => b.textContent.toLowerCase().includes('herunterladen') && !b.disabled);
    if (b) b.click(); }"""


def _neu_erzeugen(auftrag: Auftrag, seite, von: str, bis: str, ziel: Path):
    auftrag.melden("(2/2) Stelle den Zeitraum ein …")
    seite.click("mat-select", timeout=5000)
    _warten(auftrag, seite, ZEITEN["klick"])
    for wahl in seite.query_selector_all('mat-option, [role="option"]'):
        if "benutzerdefiniert" in (wahl.inner_text() or "").lower():
            wahl.click()
            break
    _warten(auftrag, seite, ZEITEN["klick"])
    seite.evaluate(FELD_SETZEN, ["mat-input-0", von])
    seite.evaluate(FELD_SETZEN, ["mat-input-1", bis])
    _warten(auftrag, seite, ZEITEN["klick"])
    vorher = seite.evaluate(ZAHL_FERTIG)
    erstellen = next((k for k in seite.query_selector_all("button")
                      if "erstellen" in (k.inner_text() or "").lower()), None)  # fmt: skip
    if not erstellen:
        raise RuntimeError("Der Knopf „Erstellen“ wurde auf der Seite nicht gefunden.")
    erstellen.click()
    beginn = time.monotonic()
    while time.monotonic() - beginn < ZEITEN["erzeugen"]:
        minuten = int((time.monotonic() - beginn) // 60)
        auftrag.melden(f"(2/2) Das Vereinsportal erzeugt den Export … ({minuten} min)")
        if seite.evaluate(ZAHL_FERTIG) > vorher:
            auftrag.melden("(2/2) Der Export ist fertig, lade herunter …")
            with seite.expect_download(timeout=ZEITEN["download"] * 1000) as geladen:
                seite.evaluate(ERSTEN_KLICKEN)
            geladen.value.save_as(str(ziel))
            return
        _warten(auftrag, seite, 1)
    raise RuntimeError("Das Vereinsportal hat den Export nicht rechtzeitig erzeugt.")


def _finanzexport(auftrag: Auftrag, kontext, seite, d: dict):
    auftrag.melden("(2/2) Öffne den Finanzexport …")
    seite.goto(d["export_url"], wait_until="domcontentloaded", timeout=30000)
    _warten(auftrag, seite, ZEITEN["export_laden"])
    if "login" in seite.url:
        raise RuntimeError("Die Anmeldung ist abgelaufen oder hat nicht geklappt.")
    ziel = auftrag.datei("finanzexport")
    fertige = _fertige_exporte(seite, d["von"], d["bis"])
    if fertige:
        auftrag.melden("(2/2) Für den Zeitraum gibt es schon einen Export, lade herunter …")
        if _vorhandenen_laden(auftrag, kontext, seite, fertige[-1], ziel):
            return
    _neu_erzeugen(auftrag, seite, d["von"], d["bis"], ziel)


def ablauf(auftrag: Auftrag, d: dict, browser_pfad: str | None = None):
    """Der ganze Abruf; läuft in einem eigenen Faden."""
    from playwright.sync_api import sync_playwright

    try:
        with sync_playwright() as p:
            browser = p.chromium.launch(
                headless=True, executable_path=browser_pfad or None,
                args=["--disable-download-notification", "--disable-popup-blocking"],
            )  # fmt: skip
            try:
                kontext = browser.new_context(accept_downloads=True)
                seite = kontext.new_page()
                try:
                    _anmelden(auftrag, seite, d)
                    if d.get("mit_liste"):
                        _spenderliste(auftrag, seite, d)
                    _finanzexport(auftrag, kontext, seite, d)
                except Abbruch:
                    raise
                except Exception as fehler:  # noqa: BLE001 – mit Schritt und Seite weitergeben
                    raise Hinweis(_beschreiben(auftrag, seite, fehler)) from fehler
            finally:
                browser.close()
        auftrag.melden("Die Dateien sind geladen.", "fertig")
    except Abbruch:
        auftrag.fehler = "Der Abruf wurde abgebrochen."
        auftrag.melden("Abgebrochen", "fehler")
    except Exception as fehler:  # noqa: BLE001 – jede Störung soll in bintafeln lesbar ankommen
        auftrag.fehler = str(fehler).splitlines()[0][:500] if str(fehler) else type(fehler).__name__
        auftrag.melden(f"Fehlgeschlagen: {auftrag.fehler}", "fehler")
    finally:
        auftrag.code = ""
        d.clear()  # Zugangsdaten nicht länger halten als nötig


PFLICHT = ("anmeldung_url", "export_url", "email", "passwort", "von", "bis")


def starten(auftrag: Auftrag, d: dict, browser_pfad: str | None = None) -> str:
    """Nimmt einen Auftrag an; liefert eine Fehlermeldung oder ''."""
    fehlt = [f for f in PFLICHT if not d.get(f)]
    if d.get("mit_liste") and not d.get("liste_url"):
        fehlt.append("liste_url")
    if fehlt:
        return f"Es fehlt: {', '.join(fehlt)}"
    if NUR_HTTPS and any(not str(d.get(f) or "https://").startswith("https://")
           for f in ("anmeldung_url", "liste_url", "export_url")):  # fmt: skip
        return "Die Adressen müssen mit https:// beginnen."
    with auftrag.sperre:
        if auftrag.stand in ("laeuft", "warte_auf_code"):
            return "Es läuft schon ein Abruf."
        nummer = auftrag.nummer + 1
        auftrag.leeren()
        auftrag.nummer = nummer
        auftrag.ordner = Path(tempfile.mkdtemp(prefix="abruf-"))
        auftrag.melden("Starte …", "laeuft")
    threading.Thread(target=ablauf, args=(auftrag, dict(d), browser_pfad), daemon=True).start()
    return ""


class Anfrage(BaseHTTPRequestHandler):
    schluessel = ""
    auftrag = AUFTRAG
    browser_pfad = None

    def log_message(self, *args):  # keine Zugriffe protokollieren
        pass

    def _antwort(self, status: int, daten: dict):
        inhalt = json.dumps(daten).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(inhalt)))
        self.end_headers()
        self.wfile.write(inhalt)

    def _erlaubt(self) -> bool:
        gesendet = self.headers.get("X-Abruf-Schluessel", "")
        if self.schluessel and hmac.compare_digest(gesendet.encode(), self.schluessel.encode()):
            return True
        self._antwort(403, {"fehler": "Schlüssel fehlt oder ist falsch."})
        return False

    def _daten(self) -> dict:
        laenge = int(self.headers.get("Content-Length") or 0)
        try:
            daten = json.loads(self.rfile.read(laenge) or b"{}") if laenge <= 65536 else {}
        except ValueError:
            daten = {}
        return daten if isinstance(daten, dict) else {}

    def do_GET(self):
        if not self._erlaubt():
            return
        a = self.auftrag
        if self.path == "/stand":
            return self._antwort(200, a.als_json())
        art = self.path.removeprefix("/datei/")
        if art in DATEIEN and a.stand == "fertig" and a.datei(art).exists():
            self.send_response(200)
            self.send_header("Content-Type", "application/octet-stream")
            self.send_header("Content-Length", str(a.datei(art).stat().st_size))
            self.end_headers()
            with a.datei(art).open("rb") as quelle:
                shutil.copyfileobj(quelle, self.wfile)
            return None
        return self._antwort(404, {"fehler": "Nicht vorhanden."})

    def do_POST(self):
        if not self._erlaubt():
            return None
        a, d = self.auftrag, self._daten()
        if self.path == "/start":
            fehler = starten(a, d, self.browser_pfad)
            return self._antwort(
                409 if fehler else 200, a.als_json() | ({"fehler": fehler} if fehler else {})
            )
        if self.path == "/code":
            code = str(d.get("code") or "").strip()
            if a.stand != "warte_auf_code" or not (code.isdigit() and len(code) == 6):
                return self._antwort(400, {"fehler": "Bitte den 6-stelligen Code eingeben."})
            a.code = code
            a.melden("2FA-Code übermittelt …", "laeuft")
            return self._antwort(200, a.als_json())
        if self.path == "/abbrechen":
            a.abbrechen = True
            return self._antwort(200, a.als_json())
        if self.path == "/fertig":
            with a.sperre:
                if a.stand in ("fertig", "fehler"):
                    a.leeren()
            return self._antwort(200, a.als_json())
        return self._antwort(404, {"fehler": "Unbekannt."})


def main():
    Anfrage.schluessel = os.environ.get("ABRUF_SCHLUESSEL", "")
    if len(Anfrage.schluessel) < 20:
        raise SystemExit(
            "BINTAFELN_ABRUF_SCHLUESSEL fehlt in der .env oder ist kürzer als 20 Zeichen."
        )
    ThreadingHTTPServer(("0.0.0.0", PORT), Anfrage).serve_forever()  # noqa: S104 – nur im Compose-Netz


if __name__ == "__main__":
    main()

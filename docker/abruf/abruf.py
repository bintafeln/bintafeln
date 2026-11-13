"""Dienst „abruf“: holt Finanzexport und Spenderliste aus WISO MeinVerein (ADR 0127).

bintafeln selbst hat keinen Browser. Dieser kleine Dienst läuft nur bei Tafeln, die ihn
einschalten (Compose-Profil ``abruf``), ist von außen nicht erreichbar und nimmt Aufträge nur mit
dem gemeinsamen Schlüssel an. Er meldet sich in WISO MeinVerein an, wartet auf den 2FA-Code,
lädt die Dateien herunter und hält sie bereit, bis bintafeln sie abgeholt hat. Zugangsdaten und
Dateien liegen nur im Arbeitsspeicher bzw. in einem vorübergehenden Ordner.

Der Ablauf (Schritte, Felder und Knöpfe der Seiten) stammt aus dem bisherigen
Spendenbelege-Programm der Tafel. Ändert WISO MeinVerein seine Seiten, muss ``ablauf()``
angepasst werden; das Hochladen von Hand in bintafeln geht immer.
"""

import hmac
import json
import os
import shutil
import tempfile
import threading
import time
import zipfile
from collections import Counter
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

PORT = 8700
NUR_HTTPS = True  # Tests gegen eine nachgebaute Seite schalten das ab
DATEIEN = {"spenderliste": "spenderliste.xlsx", "finanzexport": "finanzexport.zip"}

# Wartezeiten in Sekunden; Tests setzen sie herunter
ZEITEN = {
    "code": 300,  # so lange wartet der Dienst auf den 2FA-Code
    "knopf": 5,  # so lange darf der Anmelde-Knopf brauchen, bis er sich anklicken lässt
    "felder": 15,  # so lange dürfen die Felder der Anmeldeseite auf sich warten lassen
    "zwei_faktor": 30,  # … und die Abfrage des 2FA-Codes nach dem Absenden
    "nach_anmeldung": 3,
    "nach_code": 4,
    "liste_laden": 20,
    "export_laden": 5,
    "klick": 1,
    "zeile": 30,  # so lange darf die Zeile des neuen Exports auf sich warten lassen
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
        self.hinweise: list[str] = []  # was nicht geklappt hat, ohne den Abruf abzubrechen
        self.versand_bau = ""  # Bauplan der Kästchen zum Versand, für die Fehlersuche

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
                "dateien": vorhanden, "nummer": self.nummer,
                "hinweise": list(self.hinweise)}  # fmt: skip


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
        ort, _, zusatz = seite.url.partition("?")
        ort += "?…" if zusatz else ""  # zeigen, dass etwas abgeschnitten wurde
    except Exception:  # noqa: BLE001 – der Browser kann schon weg sein
        ort = ""
    return f"{text} (Seite: {ort})"[:500] if ort else text[:500]


KNOPF = (
    'form:has(input[name="eml-user"]) input[type="submit"], '
    'form:has(input[name="eml-user"]) button[type="submit"]'
)
# Was liegt über der Mitte des Elements? (z. B. ein Cookie-Hinweis über dem Anmelde-Knopf)
DARUEBER = """el => { const r = el.getBoundingClientRect();
    const o = document.elementFromPoint(r.left + r.width / 2, r.top + r.height / 2);
    if (!o || o === el || el.contains(o)) return '';
    return (o.tagName + (o.id ? '#' + o.id : '') + (typeof o.className === 'string' && o.className
        ? '.' + o.className.trim().split(/\\s+/).slice(0, 3).join('.') : '')).slice(0, 120); }"""


FORMULAR_ABSENDEN = """() => { const f = document.querySelector('input[name="eml-user"]')?.form;
    if (!f) return false; f.requestSubmit(); return true; }"""


def _absenden(seite):
    """Schickt die Anmeldung ab. Erst der gewöhnliche Klick; lässt sich der Knopf nicht anklicken
    (verdeckt, etwa von einem Cookie-Hinweis), ein Klick direkt auf dem Knopf; gibt es keinen
    passenden Knopf, wird das Formular direkt abgeschickt (ohne Formular: Eingabetaste)."""
    knopf = seite.locator(KNOPF).first
    try:
        knopf.click(timeout=ZEITEN["knopf"] * 1000)
        return
    except Exception as fehler:  # noqa: BLE001 – dann auf anderem Weg absenden
        grund = str(fehler).splitlines()[0]
    if knopf.count():
        darueber = knopf.evaluate(DARUEBER)
        print(f"[abruf] Anmelde-Knopf nicht anklickbar ({grund}); darüber liegt: "
              f"{darueber or 'nichts Erkennbares'}. Klicke direkt.", flush=True)  # fmt: skip
        knopf.evaluate("el => el.click()")
    else:
        print("[abruf] Kein Anmelde-Knopf gefunden; sende das Formular direkt ab.", flush=True)
        # Ohne Knopf schickt die Eingabetaste ein Formular mit zwei Feldern nicht ab
        if not seite.evaluate(FORMULAR_ABSENDEN):
            seite.press('input[name="psw-user"]', "Enter")


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
    _absenden(seite)
    seite.wait_for_load_state("domcontentloaded", timeout=15000)
    _warten(auftrag, seite, ZEITEN["nach_anmeldung"])
    # Erst nach dem Code fragen, wenn WISO MeinVerein ihn wirklich haben will. Sonst wartet
    # der Mensch fünf Minuten auf einen Code, den das Portal nie verschickt hat.
    auftrag.melden("Warte auf die Abfrage des 2FA-Codes …")
    if not _da(seite, 'input[name="twoFactorActivate"]', ZEITEN["zwei_faktor"]):
        raise Hinweis(
            "Nach dem Absenden von E-Mail und Passwort hat WISO MeinVerein nicht nach dem "
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
    # focus statt Klick: Ein Hinweis über der Seite darf das Feld nicht blockieren
    seite.focus('input[name="twoFactorActivate"]')
    seite.keyboard.type(auftrag.code, delay=150)
    _warten(auftrag, seite, ZEITEN["klick"] * 2)
    seite.evaluate("document.getElementById('ms-two-factor-submit').removeAttribute('disabled')")
    seite.evaluate("document.getElementById('ms-two-factor-submit').click()")
    _warten(auftrag, seite, ZEITEN["nach_code"])


# Die kleinen Knöpfe mit Symbol über der Liste; je nach Stand des Portals heißen sie anders
LISTEN_KNOEPFE = ", ".join(
    f"{k}:not(.disabled):not([disabled])"
    for k in ("button.mat-icon-button", "button.mat-mdc-icon-button", "button[mat-icon-button]")
)
KNOEPFE_ZEIGEN = """() => { const alle = [...document.querySelectorAll('button')];
    return alle.length + ' Knöpfe; ' + alle.slice(0, 12).map(b =>
        (typeof b.className === 'string' ? b.className.trim().split(/\\s+/).slice(0, 3).join('.')
                                         : '') || '-').join(' | '); }"""


def _spenderliste(auftrag: Auftrag, seite, d: dict):
    auftrag.melden("(1/2) Öffne die Spenderliste …")
    seite.goto(d["liste_url"], wait_until="domcontentloaded", timeout=30000)
    _warten(auftrag, seite, ZEITEN["liste_laden"])
    if "login" in seite.url:
        raise Hinweis("Die Anmeldung hat nicht geklappt. War der 2FA-Code richtig?")
    knoepfe = seite.query_selector_all(LISTEN_KNOEPFE)
    if len(knoepfe) <= 3:
        # Für die Fehlersuche: Was für Knöpfe hat die Seite überhaupt?
        print(f"[abruf] Spenderliste: {len(knoepfe)} passende Knöpfe auf "
              f"{seite.url.split('?')[0]}; vorhanden: {seite.evaluate(KNOEPFE_ZEIGEN)}",
              flush=True)  # fmt: skip
        auftrag.hinweise.append(
            "Die Liste „Spender mit E-Mail“ wurde nicht geholt: Auf der Seite fehlt der Knopf "
            "zum Exportieren. Stimmt die „Adresse der Liste“ in den Einstellungen? Die Liste "
            "lässt sich weiterhin von Hand hochladen."
        )
        auftrag.melden("(1/2) Export-Knopf der Spenderliste nicht gefunden")
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


# Die beiden Datumsfelder finden und markieren. Ihre Nummern (mat-input-0, -1 …) vergibt die
# Seite der Reihe nach, sie hängen davon ab, was vorher geöffnet war – darauf ist kein Verlass.
FELDER_FINDEN = """() => {
    const sichtbar = e => e.offsetParent !== null;
    const alle = [...document.querySelectorAll('input')].filter(sichtbar);
    let f = alle.filter(e => e.classList.contains('mat-datepicker-input')
        || e.hasAttribute('data-mat-calendar') || e.getAttribute('aria-haspopup') === 'dialog');
    if (f.length < 2)
        f = ['mat-input-0', 'mat-input-1'].map(i => document.getElementById(i)).filter(Boolean);
    if (f.length < 2) f = alle.filter(e => e.id.startsWith('mat-input-'));
    f = f.slice(0, 2);
    f.forEach((e, i) => e.setAttribute('data-abruf-datum', i));
    return {gefunden: f.length,
            alle: alle.slice(0, 12).map(e => [e.id, e.type, e.placeholder].join('/')).join(' | ')};
}"""
FELD_SETZEN = """([nummer, wert]) => {
    const feld = document.querySelector('[data-abruf-datum="' + nummer + '"]');
    Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value').set
        .call(feld, wert);
    for (const art of ['input', 'change', 'blur'])
        feld.dispatchEvent(new Event(art, {bubbles: true}));
}"""
FELD_LESEN = """n => document.querySelector('[data-abruf-datum="' + n + '"]')?.value || ''"""
ZEITRAEUME = """() => [...document.querySelectorAll('table tr em')].map(e => e.innerText.trim())"""

# Spalten, ohne die bintafeln nicht erfährt, was in WISO MeinVerein schon versendet ist. Sie stehen
# unter „Erweiterte Einstellungen → Spalten“ und sind dort anfangs nicht angekreuzt.
VERSANDSPALTEN = ("Versendet am", "SQ-verschickt", "SQ-erstellt Datum")
# Kreuzt die genannten Kästchen an, die es gibt und die noch nicht angekreuzt sind. Ergebnis:
# welche fehlen und welche angeklickt wurden.
SPALTEN_ANKREUZEN = """([namen, klicken]) => {
    // Gesucht wird über die Beschriftung, denn die Kästchen von WISO MeinVerein sind eigene
    // Bausteine. Alle Elemente, auch in offenen Shadow-DOMs.
    const norm = t => (t || '').replace(/\\s+/g, ' ').trim().toLowerCase();
    const alle = [];
    const sammeln = wurzel => {
        for (const e of wurzel.querySelectorAll('*')) {
            alle.push(e);
            if (e.shadowRoot) sammeln(e.shadowRoot);
        }
    };
    sammeln(document);
    const text = e => norm(e.innerText || e.textContent);
    const klasse = e => (typeof e.className === 'string' ? e.className
        : (e.className && e.className.baseVal) || '');
    const STEUER = 'input[type=checkbox], [role=checkbox], [aria-checked], mat-checkbox, '
        + '.mat-mdc-checkbox, .mat-checkbox';
    // das innerste Element mit genau dieser Beschriftung
    const beschriftung = name => {
        const n = norm(name), t = alle.filter(e => text(e) === n);
        return t.length ? t[t.length - 1] : null;
    };
    // eigene Bausteine erkennt man meist an „checkbox“ in der Klasse
    const AEHNLICH = '[class*=checkbox], [class*=check-box], [class*=Checkbox]';
    // das Kästchen dazu: in der Beschriftung oder bis zu vier Ebenen darüber
    const kaestchen = e => {
        for (const sel of [STEUER, AEHNLICH])
            for (let a = e, i = 0; a && i < 5; i++, a = a.parentElement) {
                const k = a.matches(sel) ? a : a.querySelector(sel);
                if (k) return k;
            }
        return null;
    };
    const angekreuzt = (k, e) => {
        if (k) {
            const f = k.matches('input') ? k : k.querySelector('input[type=checkbox]');
            if (f) return f.checked;
            const mit = k.hasAttribute('aria-checked') ? k : k.querySelector('[aria-checked]');
            if (mit) return mit.getAttribute('aria-checked') === 'true';
        }
        for (let a = k || e, i = 0; a && i < 4; i++, a = a.parentElement)
            if (/(^|[-_\\s])(checked|selected)(\\s|$)/i.test(klasse(a))) return true;
        return null;  // nicht zu erkennen
    };
    // Bauplan für die Fehlersuche: nur Bausteine, Klassen und Zustände, keine Inhalte
    const bau = e => {
        const teile = [];
        for (let a = e, i = 0; a && i < 5; i++, a = a.parentElement) {
            const kl = klasse(a).trim().split(/\\s+/).filter(Boolean).slice(0, 3).join('.');
            const at = ['role', 'aria-checked', 'type'].filter(x => a.hasAttribute(x))
                .map(x => '[' + x + '=' + a.getAttribute(x) + ']').join('');
            teile.push(a.tagName.toLowerCase() + (kl ? '.' + kl : '') + at);
        }
        return teile.reverse().join(' > ');
    };
    const fehlen = [], geklickt = [], aus = [], unklar = [], bauplaene = [];
    for (const name of namen) {
        const e = beschriftung(name);
        if (!e) { fehlen.push(name); continue; }
        const k = kaestchen(e), an = angekreuzt(k, e);
        bauplaene.push(name + ': ' + bau(k || e));
        if (an === false) aus.push(name);
        if (an === null) unklar.push(name);
        if (klicken && an !== true) {
            const ziel = k ? (k.matches('input') ? k
                : k.querySelector('input[type=checkbox]') || k) : e;
            ziel.click();
            geklickt.push(name);
        }
    }
    return {fehlen, geklickt, aus, unklar, bauplaene,
            steuer: alle.filter(e => e.matches(STEUER)).length};
}"""
# Klappt „Erweiterte Einstellungen“ auf. Die Überschrift kann ein Symbol als Text enthalten
# (z. B. „expand_more“), deshalb zählt der Anfang; geklickt wird auf das kleinste Element damit
# oder seinen anklickbaren Rahmen.
ERWEITERT_OEFFNEN = """() => {
    const norm = t => (t || '').replace(/\\s+/g, ' ').trim().toLowerCase();
    const treffer = [...document.querySelectorAll('body *')].filter(e => {
        const t = norm(e.innerText);
        return t.startsWith('erweiterte einstellungen') && t.length <= 45;
    });
    if (!treffer.length) return false;
    const kopf = treffer[treffer.length - 1];
    (kopf.closest('button, [role=button], mat-expansion-panel-header, '
        + '.mat-expansion-panel-header') || kopf).click();
    return true;
}"""


def _zeitraum_einstellen(auftrag: Auftrag, seite, von: str, bis: str):
    seite.click("mat-select", timeout=5000)
    _warten(auftrag, seite, ZEITEN["klick"])
    gewaehlt = False
    for wahl in seite.query_selector_all('mat-option, [role="option"]'):
        if "benutzerdefiniert" in (wahl.inner_text() or "").lower():
            wahl.click()
            gewaehlt = True
            break
    if not gewaehlt:
        raise Hinweis("Die Auswahl „Benutzerdefiniert“ für den Zeitraum wurde nicht gefunden.")
    _warten(auftrag, seite, ZEITEN["klick"])
    felder = seite.evaluate(FELDER_FINDEN)
    if felder["gefunden"] < 2:
        raise Hinweis(
            "Die beiden Datumsfelder für den Zeitraum wurden nicht gefunden. Felder der Seite: "
            f"{felder['alle'] or 'keine'}"
        )
    seite.evaluate(FELD_SETZEN, [0, von])
    seite.evaluate(FELD_SETZEN, [1, bis])
    _warten(auftrag, seite, ZEITEN["klick"])
    steht = [seite.evaluate(FELD_LESEN, 0), seite.evaluate(FELD_LESEN, 1)]
    if steht != [von, bis]:
        raise Hinweis(
            f"Der Zeitraum ließ sich nicht einstellen: In den Feldern steht „{steht[0]}“ bis "
            f"„{steht[1]}“ statt {von} bis {bis}."
        )


def _versandspalten(auftrag: Auftrag, seite) -> None:
    """Die Spalten „Versendet am“, „SQ-verschickt“ und „SQ-erstellt Datum“ ankreuzen (unter
    „Erweiterte Einstellungen“, die nur aufgeklappt werden, wenn die Spalten nicht zu sehen sind
    – ein Klick auf einen offenen Bereich klappt ihn zu). Klappt das nicht, läuft der Abruf
    weiter, aber mit einem Hinweis samt Bauplan der Seite für die Fehlersuche."""
    namen = list(VERSANDSPALTEN)
    stand = seite.evaluate(SPALTEN_ANKREUZEN, [namen, False])
    aufgeklappt = None
    if stand["fehlen"]:
        aufgeklappt = seite.evaluate(ERWEITERT_OEFFNEN)
        for _ in range(3):  # der Bereich kann sich langsam öffnen
            _warten(auftrag, seite, ZEITEN["klick"])
            stand = seite.evaluate(SPALTEN_ANKREUZEN, [namen, False])
            if not stand["fehlen"]:
                break
    if not stand["fehlen"]:
        stand = seite.evaluate(SPALTEN_ANKREUZEN, [namen, True])
        _warten(auftrag, seite, ZEITEN["klick"])
    danach = seite.evaluate(SPALTEN_ANKREUZEN, [namen, False])
    auftrag.versand_bau = f"Kästchen auf der Seite: {danach['steuer']}; " + " | ".join(
        danach["bauplaene"] or ["keine Beschriftung gefunden"]
    )
    # Für die Fehlersuche ins Protokoll des Dienstes: nur Bausteine der Seite, keine Daten
    print(
        f"[abruf] Spalten: fehlen {danach['fehlen']}, angeklickt {stand['geklickt']}, "
        f"danach aus {danach['aus']}, Stand unklar {danach['unklar']}, „Erweiterte "
        f"Einstellungen“ aufgeklappt: {aufgeklappt}; {auftrag.versand_bau}",
        flush=True,
    )
    nicht = danach["fehlen"] or danach["aus"]
    if nicht:
        auftrag.hinweise.append(
            "Im Finanzexport ließen sich die Spalten „" + "“, „".join(nicht) + "“ nicht "
            "ankreuzen (unter „Erweiterte Einstellungen → Spalten“). Ohne sie erfährt bintafeln "
            "nicht, welche Belege in WISO MeinVerein schon versendet sind. "
            + ("„Erweiterte Einstellungen“ wurde nicht gefunden. " if aufgeklappt is False
               else "")
            + f"Für die Fehlersuche: {auftrag.versand_bau}"
        )  # fmt: skip


def _neu_erzeugen(auftrag: Auftrag, kontext, seite, von: str, bis: str, ziel: Path,
                  ohne=()):  # fmt: skip
    """Neuen Export erzeugen; ``ohne`` sind Knöpfe schon vorhandener Exporte desselben
    Zeitraums, die nicht gemeint sind (ihnen fehlen die Spalten zum Versand)."""
    auftrag.melden(f"(2/2) Stelle den Zeitraum ein: {von} bis {bis} …")
    _zeitraum_einstellen(auftrag, seite, von, bis)
    _versandspalten(auftrag, seite)
    for knopf in ohne:
        knopf.evaluate("el => el.setAttribute('data-abruf-alt', '')")
    vorher = Counter(seite.evaluate(ZEITRAEUME))
    erstellen = next((k for k in seite.query_selector_all("button")
                      if "erstellen" in (k.inner_text() or "").lower()), None)  # fmt: skip
    if not erstellen:
        raise Hinweis("Der Knopf „Erstellen“ wurde auf der Seite nicht gefunden.")
    erstellen.click()
    beginn = time.monotonic()
    while (vergangen := time.monotonic() - beginn) < ZEITEN["erzeugen"]:
        auftrag.melden(
            f"(2/2) WISO MeinVerein erzeugt den Export {von} bis {bis} … "
            f"({int(vergangen // 60)} min)"
        )
        # Nur der Export mit genau diesem Zeitraum zählt – nicht irgendein fertiger der Seite
        fertige = [k for k in _fertige_exporte(seite, von, bis)
                   if k.get_attribute("data-abruf-alt") is None]  # fmt: skip
        if fertige:
            auftrag.melden("(2/2) Der Export ist fertig, lade herunter …")
            if _vorhandenen_laden(auftrag, kontext, seite, fertige[-1], ziel):
                return
            raise Hinweis("Der fertige Export ließ sich nicht herunterladen.")
        # Zeilen, die seit „Erstellen“ dazugekommen sind (gezählt, weil es denselben Zeitraum
        # schon geben kann): Ist keine davon unsere, hat das Portal den Zeitraum nicht übernommen
        neue = list((Counter(seite.evaluate(ZEITRAEUME)) - vorher).elements())
        if neue and vergangen > ZEITEN["zeile"] and not any(von in z and bis in z for z in neue):
            raise Hinweis(
                f"WISO MeinVerein hat einen Export für einen anderen Zeitraum angelegt "
                f"{neue[0]} statt {von} bis {bis}. Der Zeitraum wurde dort nicht übernommen."
            )
        _warten(auftrag, seite, 1)
    raise Hinweis("WISO MeinVerein hat den Export nicht rechtzeitig erzeugt.")


def _inhalt_melden(ziel: Path) -> None:
    """Was im geladenen Export steckt – nur Zahlen, keine Dateinamen (für die Fehlersuche)."""
    try:
        with zipfile.ZipFile(ziel) as archiv:
            namen = [i.filename.lower() for i in archiv.infolist() if not i.is_dir()]
    except (OSError, zipfile.BadZipFile):
        print(f"[abruf] Finanzexport: {ziel.stat().st_size} Bytes, kein ZIP-Archiv.", flush=True)
        return
    pdfs = [n for n in namen if n.endswith(".pdf")]
    belege = [n for n in pdfs if "spenden" in n]
    print(f"[abruf] Finanzexport: {len(namen)} Dateien, davon {len(pdfs)} PDF, "
          f"{len(belege)} Spendenbelege, Spalten zum Versand: "
          f"{'ja' if mit_versand(ziel) else 'nein'}.", flush=True)  # fmt: skip


def mit_versand(ziel: Path) -> bool:
    """Steckt im Export eine Excel-Datei mit den Spalten zum Versand? Nur in den Texten der
    Excel-Datei gesucht (eine .xlsx ist selbst ein ZIP), ohne weitere Abhängigkeit."""
    gesucht = [n.encode() for n in VERSANDSPALTEN]
    try:
        with zipfile.ZipFile(ziel) as archiv:
            for eintrag in archiv.infolist():
                if not eintrag.filename.lower().endswith(".xlsx"):
                    continue
                with zipfile.ZipFile(archiv.open(eintrag)) as mappe:
                    for teil in mappe.namelist():
                        if teil.endswith(".xml") and any(g in mappe.read(teil) for g in gesucht):
                            return True
    except (OSError, zipfile.BadZipFile):
        return False
    return False


def _finanzexport(auftrag: Auftrag, kontext, seite, d: dict):
    auftrag.melden("(2/2) Öffne den Finanzexport …")
    seite.goto(d["export_url"], wait_until="domcontentloaded", timeout=30000)
    _warten(auftrag, seite, ZEITEN["export_laden"])
    if "login" in seite.url:
        raise RuntimeError("Die Anmeldung ist abgelaufen oder hat nicht geklappt.")
    ziel = auftrag.datei("finanzexport")
    fertige = _fertige_exporte(seite, d["von"], d["bis"])
    if fertige:
        auftrag.melden(
            f"(2/2) Für {d['von']} bis {d['bis']} gibt es schon einen Export, lade herunter …"
        )
        if _vorhandenen_laden(auftrag, kontext, seite, fertige[-1], ziel) and mit_versand(ziel):
            _inhalt_melden(ziel)
            return
        # ohne die Spalten zum Versand neu erzeugen, sonst bliebe „versendet“ leer
        auftrag.melden("(2/2) Dem vorhandenen Export fehlen die Spalten zum Versand, erzeuge neu …")
        seite.goto(d["export_url"], wait_until="domcontentloaded", timeout=30000)
        _warten(auftrag, seite, ZEITEN["export_laden"])
        fertige = _fertige_exporte(seite, d["von"], d["bis"])
    _neu_erzeugen(auftrag, kontext, seite, d["von"], d["bis"], ziel, ohne=fertige)
    _inhalt_melden(ziel)
    if not mit_versand(ziel) and not any("ankreuzen" in h for h in auftrag.hinweise):
        auftrag.hinweise.append(
            "Die Kästchen für „Versendet am“, „SQ-verschickt“ und „SQ-erstellt Datum“ wurden "
            "angeklickt, der Export enthält die Spalten aber trotzdem nicht. Für die "
            f"Fehlersuche: {auftrag.versand_bau}"
        )


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

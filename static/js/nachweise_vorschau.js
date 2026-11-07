// Vorschau der Nachweise: Ein Foto oder PDF (Link mit data-bild) öffnet beim Klick groß als Popup
// über der Seite – bei einem PDF wird die gerenderte erste Seite gezeigt (data-vorschau). Andere
// Dateien (data-fenster) öffnen in einem eigenen Fenster. Ohne JavaScript bleibt es ein normaler
// Link, der die Datei in einem neuen Tab öffnet.
//
// Auf der Ausweisprüfungsseite trägt das Vorschaubild zusätzlich data-bescheid-url (als Bescheid
// einordnen), data-neu-pruefen-url (diesen einen Ausweis erneut automatisch prüfen),
// data-bereich-url (einen Bildausschnitt gezielt lesen) und data-uebernehmen-url (erkannte
// Staatsangehörigkeit in den Antrag übernehmen). Dann bietet das Popup die passenden Knöpfe; nach
// einer Aktion bleibt man auf der aktuellen Seite (bzw. die Seite lädt neu).
(function () {
  "use strict";
  if (window.__nachweisVorschau) return; // nur einmal binden (das Skript kann mehrfach eingebunden sein)
  window.__nachweisVorschau = true;

  var dialog, bild, huelle, auswahl, status, bescheid, neu, bereich, staatAuswahl, uebernehmen, link;
  var urls = {}; // bescheid, neu, bereich, uebernehmen für das aktuell gezeigte Bild
  var staatenGefuellt = false; // die Länderliste wird einmal aus der Seitenvorlage geklont
  var erkannt = ""; // zuletzt im Ausschnitt erkanntes Land
  var zieht = false, startX = 0, startY = 0;

  function marke() {
    var m = document.querySelector("input[name=csrfmiddlewaretoken]");
    return m ? m.value : "";
  }

  function senden(url, felder) {
    var daten = new FormData();
    daten.append("csrfmiddlewaretoken", marke());
    Object.keys(felder).forEach(function (k) { daten.append(k, felder[k]); });
    return fetch(url, { method: "POST", body: daten, headers: { "X-CSRFToken": marke() } });
  }

  function hier() { return window.location.pathname + window.location.search; }

  // "Ist ein Bescheid": als Amtsdokument einordnen. Das Popup geht sofort zu (schnelles Gefühl),
  // die Seite lädt danach im Hintergrund neu, damit die Zeile verschwindet.
  function alsBescheid(url) {
    dialog.close();
    senden(url, { weiter: hier() }).then(function () { window.location.reload(); });
  }

  function zeichnenAn(an) {
    huelle.classList.toggle("zeichnen", an);
    auswahl.hidden = true;
    if (an) {
      status.textContent = "Ziehen Sie ein Rechteck über die Staatsangehörigkeit im Bild.";
      uebernehmen.hidden = true;
      erkannt = "";
    }
  }

  function rechteck(e) {
    var r = bild.getBoundingClientRect();
    var x = Math.max(r.left, Math.min(r.right, e.clientX));
    var y = Math.max(r.top, Math.min(r.bottom, e.clientY));
    return { r: r, x: x, y: y };
  }

  function lesen(r, x1, y1, x2, y2) {
    var x = (Math.min(x1, x2) - r.left) / r.width;
    var y = (Math.min(y1, y2) - r.top) / r.height;
    var b = Math.abs(x2 - x1) / r.width;
    var h = Math.abs(y2 - y1) / r.height;
    if (b < 0.02 || h < 0.02) { zeichnenAn(true); return; } // zu klein → noch mal
    status.textContent = "Lese …";
    senden(urls.bereich, { x: x, y: y, b: b, h: h })
      .then(function (a) { return a.json(); })
      .then(function (d) {
        erkannt = (d && d.land) || "";
        if (erkannt) {
          status.textContent = "Erkannt: " + erkannt + ".";
          uebernehmen.textContent = "„" + erkannt + "“ übernehmen";
          uebernehmen.hidden = !urls.uebernehmen;
          staatAuswahl.value = erkannt; // in der Auswahl mitführen (falls das Land dort steht)
        } else {
          status.textContent = "Nichts erkannt – anderen Bereich versuchen.";
          uebernehmen.hidden = true;
        }
      })
      .catch(function () { status.textContent = "Lesen fehlgeschlagen."; });
  }

  function bauen() {
    dialog = document.createElement("dialog");
    dialog.className = "nachweis-dialog";
    huelle = document.createElement("div");
    huelle.className = "nachweis-bild-huelle";
    bild = document.createElement("img");
    bild.alt = "";
    bild.draggable = false;
    auswahl = document.createElement("div");
    auswahl.className = "nachweis-auswahl";
    auswahl.hidden = true;
    huelle.append(bild, auswahl);
    status = document.createElement("div");
    status.className = "nachweis-status";
    var leiste = document.createElement("div");
    leiste.className = "nachweis-dialog-leiste";
    bescheid = knopf("📄 Ist ein Bescheid");
    neu = knopf("🔄 Neu prüfen");
    bereich = knopf("🔍 Nationalität im Bild lesen");
    staatAuswahl = document.createElement("select");
    staatAuswahl.className = "nachweis-staat-auswahl";
    fuelleStaaten();
    uebernehmen = knopf("Übernehmen");
    uebernehmen.className = "knopf knopf-klein";
    link = document.createElement("a");
    link.target = "_blank";
    link.rel = "noopener";
    link.className = "knopf knopf-zweitrangig";
    link.textContent = "In neuem Fenster öffnen";
    var zu = knopf("Schließen");
    zu.className = "knopf knopf-abbrechen";
    leiste.append(bescheid, neu, bereich, staatAuswahl, uebernehmen, link, zu);
    dialog.append(huelle, status, leiste);
    document.body.appendChild(dialog);

    zu.addEventListener("click", function () { dialog.close(); });
    dialog.addEventListener("click", function (e) { if (e.target === dialog) dialog.close(); });
    bescheid.addEventListener("click", function () { if (urls.bescheid) alsBescheid(urls.bescheid); });
    neu.addEventListener("click", function () {
      if (!urls.neu) return;
      neu.disabled = true;
      status.textContent = "Prüfe erneut …";
      senden(urls.neu, {})
        .then(function (a) { return a.json(); })
        .then(function (d) {
          status.textContent = (d && d.text) || "Erneut geprüft.";
          // kurz anzeigen, dann die Seite neu laden, damit die Zeile das neue Ergebnis zeigt
          setTimeout(function () { window.location.reload(); }, 1200);
        })
        .catch(function () { status.textContent = "Prüfung fehlgeschlagen."; neu.disabled = false; });
    });
    bereich.addEventListener("click", function () { zeichnenAn(!huelle.classList.contains("zeichnen")); });
    // Land von Hand aus der Auswahl wählen: wie ein erkanntes Land behandeln (Übernehmen zeigen).
    staatAuswahl.addEventListener("change", function () {
      erkannt = staatAuswahl.value || "";
      if (erkannt && urls.uebernehmen) {
        uebernehmen.textContent = "„" + erkannt + "“ übernehmen";
        uebernehmen.hidden = false;
        status.textContent = "";
      } else {
        uebernehmen.hidden = true;
      }
    });
    uebernehmen.addEventListener("click", function () {
      if (!erkannt || !urls.uebernehmen) return;
      senden(urls.uebernehmen, { staatsangehoerigkeit: erkannt }).then(function () {
        window.location.reload();
      });
    });

    huelle.addEventListener("pointerdown", function (e) {
      if (!huelle.classList.contains("zeichnen")) return;
      e.preventDefault();
      var p = rechteck(e);
      zieht = true; startX = p.x; startY = p.y;
      auswahl.hidden = false;
      stellen(p.r, startX, startY, startX, startY);
      huelle.setPointerCapture(e.pointerId);
    });
    huelle.addEventListener("pointermove", function (e) {
      if (!zieht) return;
      var p = rechteck(e);
      stellen(p.r, startX, startY, p.x, p.y);
    });
    huelle.addEventListener("pointerup", function (e) {
      if (!zieht) return;
      zieht = false;
      var p = rechteck(e);
      huelle.classList.remove("zeichnen");
      lesen(p.r, startX, startY, p.x, p.y);
    });
  }

  function knopf(text) {
    var b = document.createElement("button");
    b.type = "button";
    b.className = "knopf knopf-zweitrangig";
    b.textContent = text;
    return b;
  }

  // Länder einmal aus der Seitenvorlage <template id="ausweis-staaten-optionen"> in die Auswahl
  // klonen. Fehlt die Vorlage (keine Berechtigung), bleibt die Auswahl leer und wird verborgen.
  function fuelleStaaten() {
    var tpl = document.getElementById("ausweis-staaten-optionen");
    if (!tpl || !tpl.content) return;
    staatAuswahl.appendChild(new Option("— Land von Hand setzen —", ""));
    tpl.content.querySelectorAll("option").forEach(function (o) {
      staatAuswahl.appendChild(o.cloneNode(true));
    });
    staatenGefuellt = staatAuswahl.options.length > 1;
  }

  function stellen(r, x1, y1, x2, y2) {
    var hr = huelle.getBoundingClientRect();
    auswahl.style.left = (Math.min(x1, x2) - hr.left) + "px";
    auswahl.style.top = (Math.min(y1, y2) - hr.top) + "px";
    auswahl.style.width = Math.abs(x2 - x1) + "px";
    auswahl.style.height = Math.abs(y2 - y1) + "px";
  }

  function popup(a) {
    if (!dialog) bauen();
    urls = {
      bescheid: a.getAttribute("data-bescheid-url") || "",
      neu: a.getAttribute("data-neu-pruefen-url") || "",
      bereich: a.getAttribute("data-bereich-url") || "",
      uebernehmen: a.getAttribute("data-uebernehmen-url") || "",
    };
    // Bei einem PDF die gerenderte erste Seite zeigen (data-vorschau); der Link „In neuem Fenster
    // öffnen" führt weiter auf die echte Datei (href).
    bild.src = a.getAttribute("data-vorschau") || a.getAttribute("href");
    bild.alt = a.getAttribute("title") || "";
    link.href = a.getAttribute("href");
    bescheid.hidden = !urls.bescheid;
    neu.hidden = !urls.neu;
    neu.disabled = false;
    bereich.hidden = !urls.bereich;
    staatAuswahl.hidden = !(staatenGefuellt && urls.uebernehmen);
    staatAuswahl.value = "";
    erkannt = "";
    uebernehmen.hidden = true;
    status.textContent = "";
    huelle.classList.remove("zeichnen");
    auswahl.hidden = true;
    dialog.showModal();
  }

  document.addEventListener("click", function (e) {
    var a = e.target.closest("a[data-bild], a[data-fenster]");
    if (!a) return;
    e.preventDefault();
    if (a.hasAttribute("data-bild")) {
      popup(a);
    } else {
      var w = window.open(a.href, "_blank", "width=900,height=1000,scrollbars=yes,resizable=yes");
      if (!w) window.open(a.href, "_blank"); // falls das Fenster blockiert wurde: normaler Tab
    }
  });
})();

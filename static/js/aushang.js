// Aushang-Monitor (ADR 0080): zeigt die Seiten nacheinander (oder je zwei nebeneinander), passt
// die Schrift so an, dass jede Seite ohne Scrollen auf den Bildschirm passt, und holt jede Minute
// den neuen Stand. Antippen (oder ein Knopf oben, je Seite einer) zeigt einen Plan groß und ganz
// (zum Lesen und Ändern); „Übersicht“ oder 30 Sekunden ohne Eingabe führen zurück. In der großen Ansicht öffnet ein Platz den Dialog zum
// Ändern mit persönlicher PIN. Ist der Link nicht mehr gültig (neuer Link erzeugt, Aushang aus),
// verschwinden die Namen sofort vom Bildschirm.
(function () {
  "use strict";

  var NEU_LADEN = 60 * 1000;
  var RUHE_GROSS = 30 * 1000; // ohne Eingabe zurück zur Übersicht
  var GANZ_NEU = 6 * 60 * 60 * 1000; // neue Programmversion: Seite ganz neu laden
  var body = document.body;
  var gleichzeitig = body.dataset.nebeneinander === "2" ? 2 : 1;
  var dauer = Math.max(5, parseInt(body.dataset.sekunden, 10) || 20) * 1000;
  var aendern = body.dataset.aendern === "1";
  var dialog = document.getElementById("aushang-dialog");
  var start = 0;
  var gross = null; // Nummer der groß gezeigten Seite
  var ruheTimer = null;

  function folien() {
    return Array.prototype.slice.call(document.querySelectorAll("#aushang-folien > .aushang-folie"));
  }

  // Größte Schrift, bei der der ganze Inhalt ohne Schieben hineinpasst (Suche zwischen 6 und
  // 60 Pixel) – in der Übersicht wie in der großen Ansicht.
  function einpassen(folie) {
    var inhalt = folie.querySelector(".aushang-inhalt");
    if (!inhalt) return;
    var klein = 6, oben = 60;
    for (var i = 0; i < 12; i++) {
      var mitte = (klein + oben) / 2;
      inhalt.style.fontSize = mitte + "px";
      var passt = inhalt.scrollWidth <= inhalt.clientWidth + 1 &&
        inhalt.scrollHeight <= inhalt.clientHeight + 1;
      if (passt) klein = mitte; else oben = mitte;
    }
    inhalt.style.fontSize = (klein * 0.98) + "px"; // etwas Luft für Rundungen
  }

  function zeigen() {
    var alle = folien();
    if (!alle.length) return;
    if (gross !== null && gross >= alle.length) gross = null;
    body.classList.toggle("aushang-gross", gross !== null);
    var sichtbar = [];
    if (gross !== null) {
      sichtbar = [gross];
    } else {
      start = start % alle.length;
      for (var i = 0; i < Math.min(gleichzeitig, alle.length); i++) sichtbar.push((start + i) % alle.length);
    }
    alle.forEach(function (f, nr) { f.classList.toggle("sichtbar", sichtbar.indexOf(nr) >= 0); });
    sichtbar.forEach(function (nr) { einpassen(alle[nr]); });
    document.querySelectorAll("#aushang-reiter button").forEach(function (knopf) {
      var aktiv = gross !== null && parseInt(knopf.dataset.nr, 10) === gross;
      knopf.classList.toggle("aktiv", aktiv);
      knopf.setAttribute("aria-pressed", aktiv ? "true" : "false");
    });
    var punkte = document.getElementById("aushang-punkte");
    punkte.innerHTML = "";
    if (gross === null && alle.length > gleichzeitig) {
      alle.forEach(function (_, nr) {
        var p = document.createElement("span");
        p.className = "aushang-punkt" + (sichtbar.indexOf(nr) >= 0 ? " aktiv" : "");
        punkte.appendChild(p);
      });
    }
  }

  function weiter() {
    if (gross === null && folien().length > gleichzeitig) {
      start += gleichzeitig;
      zeigen();
    }
  }

  function grossZeigen(nr) {
    var anzahl = folien().length;
    gross = ((nr % anzahl) + anzahl) % anzahl;
    zeigen();
    bewegt();
  }

  function zurUebersicht() {
    if (dialog.open) dialog.close();
    gross = null;
    clearTimeout(ruheTimer);
    zeigen();
  }

  // Jede Eingabe in der großen Ansicht verlängert die Zeit bis zur Rückkehr
  function bewegt() {
    clearTimeout(ruheTimer);
    if (gross !== null) ruheTimer = setTimeout(zurUebersicht, RUHE_GROSS);
  }

  function meldung(text) {
    var m = document.getElementById("aushang-meldung");
    m.textContent = text;
    m.hidden = false;
    clearTimeout(meldung.timer);
    meldung.timer = setTimeout(function () { m.hidden = true; }, 6000);
  }

  function csrf() {
    var feld = document.querySelector("input[name=csrfmiddlewaretoken]");
    return feld ? feld.value : "";
  }

  function platzOeffnen(kennung) {
    var url = body.dataset.platzUrl + "?platz=" + encodeURIComponent(kennung);
    fetch(url, { cache: "no-store", credentials: "same-origin", headers: { "X-Aushang": "1" } })
      .then(function (antwort) { return antwort.status === 200 ? antwort.text() : null; })
      .then(function (html) {
        if (!html) { meldung("Dieser Platz lässt sich hier nicht ändern."); return; }
        dialog.innerHTML = html;
        dialog.showModal();
        var erstes = dialog.querySelector("select, input[type=password]");
        if (erstes) erstes.focus();
      })
      .catch(function () { meldung("Keine Verbindung. Bitte gleich noch einmal versuchen."); });
  }

  function absenden(form, knopf) {
    var daten = new FormData(form);
    if (knopf && knopf.name) daten.set(knopf.name, knopf.value);
    fetch(body.dataset.platzUrl, {
      method: "POST", body: daten, credentials: "same-origin",
      headers: { "X-Aushang": "1", "X-CSRFToken": csrf() },
    })
      .then(function (antwort) { return antwort.status === 200 ? antwort.json() : null; })
      .then(function (ergebnis) {
        if (!ergebnis) { meldung("Ändern ist hier nicht mehr möglich."); dialog.close(); return; }
        if (!ergebnis.ok) {
          var fehler = dialog.querySelector(".aushang-fehler");
          fehler.textContent = ergebnis.fehler;
          fehler.hidden = false;
          var pin = form.querySelector("input[name=pin]");
          if (pin) { pin.value = ""; pin.focus(); }
          return;
        }
        dialog.close();
        meldung(ergebnis.meldung);
        neuLaden();
      })
      .catch(function () { meldung("Keine Verbindung. Bitte gleich noch einmal versuchen."); });
  }

  function neuLaden() {
    if (dialog.open) return; // nicht mitten im Eintragen umbauen
    fetch(window.location.href, { cache: "no-store", credentials: "same-origin",
                                  headers: { "X-Aushang": "1" } })
      .then(function (antwort) {
        if (antwort.status === 204) {
          document.getElementById("aushang-folien").innerHTML =
            '<section class="aushang-folie sichtbar aushang-leer"><h1>Dieser Link ist nicht mehr gültig.</h1></section>';
          document.getElementById("aushang-punkte").innerHTML = "";
          gross = null;
          body.classList.remove("aushang-gross");
          return null;
        }
        return antwort.ok ? antwort.text() : null;
      })
      .then(function (html) {
        if (!html || dialog.open) return;
        var neu = new DOMParser().parseFromString(html, "text/html");
        var inhalt = neu.getElementById("aushang-folien");
        if (!inhalt) return;
        document.getElementById("aushang-folien").innerHTML = inhalt.innerHTML;
        document.getElementById("aushang-reiter").innerHTML = neu.getElementById("aushang-reiter").innerHTML;
        document.getElementById("aushang-stand").textContent = neu.getElementById("aushang-stand").textContent;
        zeigen();
      })
      .catch(function () { /* Netz kurz weg: alter Stand bleibt stehen, nächster Versuch in einer Minute */ });
  }

  function vollbildKnopf() {
    var knopf = document.getElementById("aushang-vollbild");
    if (!knopf || !document.fullscreenEnabled) return;
    knopf.hidden = !!document.fullscreenElement;
  }

  // Antippen: in der Übersicht eine Seite groß zeigen, in der großen Ansicht einen Platz ändern
  document.getElementById("aushang-folien").addEventListener("click", function (e) {
    var folie = e.target.closest(".aushang-folie");
    if (!folie || folie.classList.contains("aushang-leer")) return;
    if (gross === null) {
      grossZeigen(parseInt(folie.dataset.nr, 10) || 0);
      return;
    }
    var zelle = e.target.closest("td, .fd-platz");
    var platz = zelle && (zelle.matches("[data-platz]") ? zelle : zelle.querySelector("[data-platz]"));
    if (aendern && platz) platzOeffnen(platz.dataset.platz);
  });
  document.getElementById("aushang-zurueck").addEventListener("click", zurUebersicht);
  document.getElementById("aushang-reiter").addEventListener("click", function (e) {
    var knopf = e.target.closest("button[data-nr]");
    if (knopf) grossZeigen(parseInt(knopf.dataset.nr, 10));
  });
  document.getElementById("aushang-vollbild").addEventListener("click", function () {
    document.documentElement.requestFullscreen().catch(function () {});
  });
  dialog.addEventListener("submit", function (e) {
    if (e.target.method === "dialog") return;
    e.preventDefault();
    absenden(e.target, e.submitter);
  });
  ["pointerdown", "keydown", "scroll", "input"].forEach(function (art) {
    document.addEventListener(art, bewegt, true);
  });

  // Mauszeiger nach kurzer Zeit ausblenden
  var ruhe = null;
  document.addEventListener("mousemove", function () {
    body.classList.remove("aushang-ruhig");
    clearTimeout(ruhe);
    ruhe = setTimeout(function () { body.classList.add("aushang-ruhig"); }, 3000);
  });

  document.addEventListener("fullscreenchange", vollbildKnopf);
  window.addEventListener("resize", zeigen);
  vollbildKnopf();
  zeigen();
  // Schriften laden manchmal erst nach dem ersten Einpassen und ändern die Maße
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(zeigen);
  setInterval(weiter, dauer);
  setInterval(neuLaden, NEU_LADEN);
  setTimeout(function () { window.location.reload(); }, GANZ_NEU);
})();

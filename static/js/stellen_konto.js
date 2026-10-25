// Tablet einer Ausgabestelle (ADR 0059): Nach 30 Minuten ohne Anfrage an den Server lädt die
// Seite neu; die StellenKontoMiddleware meldet dann ab, und es bleiben keine Kundendaten stehen.
// Jede HTMX-Anfrage (z. B. am Einlass) zählt als Eingabe und startet die Zeit neu.
(function () {
  "use strict";
  var skript = document.currentScript;
  var ms = (parseInt(skript && skript.dataset.sekunden, 10) || 1805) * 1000;
  var zeit = null;
  function starten() {
    if (zeit) window.clearTimeout(zeit);
    zeit = window.setTimeout(function () { window.location.reload(); }, ms);
  }
  starten();
  document.addEventListener("htmx:afterRequest", starten);
})();

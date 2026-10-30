// Nach einer htmx-Aktion im Einlass (das ganze #einlass wird ausgetauscht) die Scroll-Position
// halten, damit die Seite nicht springt – z. B. nach „Korrekturwunsch senden" weiter unten in den
// Angaben eines Kunden (ADR 0035). Ohne htmx/JS bleibt alles wie bisher.
(function () {
  "use strict";
  var y = null;

  function imEinlass(e) {
    var ziel = e.detail && e.detail.target;
    return !!(ziel && (ziel.id === "einlass" || (ziel.closest && ziel.closest("#einlass"))));
  }

  document.body.addEventListener("htmx:beforeSwap", function (e) {
    if (imEinlass(e)) y = window.scrollY;
  });

  document.body.addEventListener("htmx:afterSettle", function (e) {
    if (y !== null && imEinlass(e)) {
      window.scrollTo(0, y);
      y = null;
    }
  });
})();

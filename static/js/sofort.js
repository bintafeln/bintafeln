// Filterformulare mit data-sofort: Eine geänderte Auswahl zeigt das Ergebnis gleich an, ohne
// „Anzeigen“. Auswahlfelder, Häkchen und Datumsfelder sofort, Zahl- und Textfelder kurz nach dem
// Tippen. Felder mit data-nicht-sofort (z. B. die Spaltenwahl) warten weiter auf den Knopf.
(function () {
  "use strict";
  var WARTEN = 700;
  document.querySelectorAll("form[data-sofort]").forEach(function (formular) {
    var zeit = null;
    function senden() {
      if (formular.requestSubmit) formular.requestSubmit(); else formular.submit();
    }
    formular.addEventListener("change", function (ereignis) {
      var feld = ereignis.target;
      if (!feld.name || feld.closest("[data-nicht-sofort]")) return;
      clearTimeout(zeit);
      if (feld.type === "number" || feld.type === "text" || feld.type === "search") {
        zeit = setTimeout(senden, WARTEN);
      } else {
        senden();
      }
    });
  });
})();

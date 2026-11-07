// Ein Feldfehler vom letzten Absenden (z. B. „mindestens eine Rolle wählen“) verschwindet sofort,
// sobald man genau dieses Feld ändert – etwa eine Rolle anhakt. Reine Browser-Rückmeldung; die
// eigentliche Prüfung macht weiter der Server beim Speichern.
(function () {
  "use strict";
  document.querySelectorAll(".feld.hat-fehler").forEach(function (feld) {
    function weg() {
      feld.classList.remove("hat-fehler");
      feld.querySelectorAll(".fehler").forEach(function (hinweis) {
        hinweis.remove();
      });
    }
    feld.addEventListener("change", weg);
    feld.addEventListener("input", weg);
  });
})();

// Fahrt beginnen (Modul Touren): Beim Wählen des Fahrzeugs den letzten bekannten Kilometerstand
// vorschlagen. Das Feld bleibt frei änderbar.
(function () {
  "use strict";
  var wahl = document.querySelector("select[data-km-ziel]");
  if (!wahl) { return; }
  var feld = document.getElementById(wahl.getAttribute("data-km-ziel"));
  var hinweis = document.getElementById("km-letzter");
  var vorschlag = "";
  function zeigen() {
    var gewaehlt = wahl.options[wahl.selectedIndex];
    var stand = gewaehlt ? gewaehlt.getAttribute("data-km") : null;
    if (feld && (feld.value === "" || feld.value === vorschlag)) {
      feld.value = stand || "";
    }
    vorschlag = stand || "";
    if (hinweis) {
      hinweis.hidden = !stand;
      hinweis.textContent = stand ? "Letzter bekannter Stand dieses Fahrzeugs: " + stand + " km. Bitte prüfen." : "";
    }
  }
  wahl.addEventListener("change", zeigen);
  zeigen();
})();

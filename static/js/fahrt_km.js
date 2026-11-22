// Fahrt beginnen (Modul Touren): Beim Wählen des Fahrzeugs den letzten bekannten Kilometerstand
// vorschlagen. Das Feld bleibt frei änderbar. Fahrzeug und Kilometerstand merkt sich das Gerät für
// diese Tour an diesem Tag, bis die Fahrt begonnen ist – wer vorher noch etwas anderes ansieht,
// muss nichts neu eintragen.
(function () {
  "use strict";
  var formular = document.querySelector("form[data-fahrt-merken]");
  var wahl = document.querySelector("select[data-km-ziel]");
  var feld = document.getElementById(wahl ? wahl.getAttribute("data-km-ziel") : "km_start");
  var VOR = "bintafeln-fahrt-";
  var schluessel = formular ? VOR + formular.getAttribute("data-fahrt-merken") : "";

  function gemerkt() {
    try {
      // Reste anderer Touren und Tage wegräumen
      for (var i = window.localStorage.length - 1; i >= 0; i--) {
        var name = window.localStorage.key(i);
        if (name && name.indexOf(VOR) === 0 && name !== schluessel) window.localStorage.removeItem(name);
      }
      return schluessel ? JSON.parse(window.localStorage.getItem(schluessel) || "null") : null;
    } catch (e) { return null; }
  }
  function merken() {
    if (!schluessel) return;
    try {
      window.localStorage.setItem(schluessel, JSON.stringify({
        fahrzeug: wahl ? wahl.value : "", km: feld ? feld.value : "",
      }));
    } catch (e) { /* privat: dann eben neu eintragen */ }
  }

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

  var alt = gemerkt();
  if (wahl) {
    if (alt && alt.fahrzeug && wahl.querySelector('option[value="' + String(alt.fahrzeug).replace(/\D/g, "") + '"]')) {
      wahl.value = alt.fahrzeug;
    }
    wahl.addEventListener("change", function () { zeigen(); merken(); });
    zeigen();
  }
  if (feld) {
    if (alt && alt.km) feld.value = alt.km;
    feld.addEventListener("input", merken);
  }
})();

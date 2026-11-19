// Filterformulare mit data-sofort: Eine geänderte Auswahl zeigt das Ergebnis gleich an, ohne
// „Anzeigen“. Auswahlfelder, Häkchen und Datumsfelder sofort, Zahl- und Textfelder kurz nach dem
// Tippen. Felder mit data-nicht-sofort (z. B. Suchfelder, die selbst beim Tippen suchen) warten
// weiter auf den Knopf. Ein aufgeklapptes <details id="…"> im Formular (z. B. „Spalten wählen“)
// bleibt nach dem Neuladen offen, damit man mehrere Häkchen nacheinander setzen kann.
(function () {
  "use strict";
  var WARTEN = 700;
  var OFFEN = "bintafeln-sofort-offen";
  try {
    var offen = document.getElementById(sessionStorage.getItem(OFFEN) || "-");
    sessionStorage.removeItem(OFFEN);
    if (offen && offen.tagName === "DETAILS") offen.open = true;
  } catch (fehler) { /* ohne Speicher: klappt eben wieder zu */ }
  document.querySelectorAll("form[data-sofort]").forEach(function (formular) {
    var zeit = null;
    function senden() {
      // Unvollständig (z. B. „Wartezeit“ noch ohne Datum): erst absenden, wenn alles passt
      if (formular.checkValidity && !formular.checkValidity()) return;
      if (formular.requestSubmit) formular.requestSubmit(); else formular.submit();
    }
    formular.addEventListener("change", function (ereignis) {
      var feld = ereignis.target;
      if (!feld.name || feld.closest("[data-nicht-sofort]")) return;
      clearTimeout(zeit);
      var klappe = feld.closest("details[id]");
      if (klappe && formular.contains(klappe)) {
        try { sessionStorage.setItem(OFFEN, klappe.id); } catch (fehler) { /* siehe oben */ }
      }
      if (feld.type === "number" || feld.type === "text" || feld.type === "search") {
        zeit = setTimeout(senden, WARTEN);
      } else {
        senden();
      }
    });
    // Aufklappbare Mehrfachauswahl (data-sofort-beim-schliessen): erst anwenden, wenn das Menü
    // wieder zugeht – so lassen sich mehrere Häkchen setzen, ohne dass die Seite dazwischen lädt.
    formular.querySelectorAll("details[data-sofort-beim-schliessen]").forEach(function (menue) {
      var geaendert = false;
      menue.addEventListener("change", function () { geaendert = true; });
      menue.addEventListener("toggle", function () {
        if (!menue.open && geaendert) { geaendert = false; senden(); }
      });
    });
  });
})();

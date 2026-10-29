// Formulare (Methode GET), deren Ergebnis in einem neuen Fenster erscheinen soll (target bzw.
// formtarget „_blank“, z. B. ein PDF), öffnen es als Link mit window.open. In der iPad-App vom
// Home-Bildschirm (ohne Tabs und Zurück-Knopf) bliebe ein abgeschicktes Formular sonst im selben
// Fenster, und man käme nicht mehr zurück. POST-Formulare bleiben, wie sie sind.
(function () {
  "use strict";
  document.addEventListener("submit", function (ereignis) {
    var formular = ereignis.target;
    var knopf = ereignis.submitter;
    var ziel = (knopf && knopf.getAttribute("formtarget")) || formular.getAttribute("target");
    var methode = (knopf && knopf.getAttribute("formmethod")) || formular.getAttribute("method");
    if (ziel !== "_blank" || (methode || "get").toLowerCase() !== "get") return;
    ereignis.preventDefault();
    var daten = new FormData(formular);
    if (knopf && knopf.name) daten.append(knopf.name, knopf.value);
    var aktion = (knopf && knopf.getAttribute("formaction")) ? knopf.formAction : formular.action;
    var abfrage = new URLSearchParams(daten).toString();
    window.open(aktion.split("?")[0] + (abfrage ? "?" + abfrage : ""), "_blank", "noopener");
  });
})();

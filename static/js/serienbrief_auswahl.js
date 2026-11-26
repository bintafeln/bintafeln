// Serienbrief erstellen: Empfänger einzeln an- und abhaken. Die Häkchen gehören zum Formular
// darüber (form="sb-form"); hier nur „Alle“/„Keinen“ und die mitlaufende Anzahl in den Knöpfen.
(function () {
  "use strict";

  var liste = document.getElementById("sb-empfaenger");
  if (!liste) return;

  function haken() { return liste.querySelectorAll('input[type="checkbox"][name="an"]'); }

  function zaehlen() {
    var anzahl = 0;
    haken().forEach(function (h) { if (h.checked) anzahl += 1; });
    document.querySelectorAll("[data-sb-anzahl]").forEach(function (e) {
      e.textContent = String(anzahl);
    });
  }

  liste.addEventListener("change", zaehlen);
  document.querySelectorAll("[data-sb-alle]").forEach(function (knopf) {
    knopf.addEventListener("click", function () {
      var an = knopf.getAttribute("data-sb-alle") === "1";
      haken().forEach(function (h) { h.checked = an; });
      zaehlen();
    });
  });
  zaehlen();
})();

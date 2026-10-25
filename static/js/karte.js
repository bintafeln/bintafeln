// Karte einer Ausgabestelle (ADR 0048): Google Maps wird erst nach Klick geladen, damit ohne
// Zustimmung keine Daten an Google gehen.
(function () {
  "use strict";
  document.addEventListener("click", function (ereignis) {
    var knopf = ereignis.target.closest("[data-karte-laden]");
    if (!knopf) return;
    var rahmen = knopf.closest("[data-karte]");
    var karte = document.createElement("iframe");
    karte.src = rahmen.getAttribute("data-karte");
    karte.title = "Karte";
    karte.loading = "lazy";
    karte.referrerPolicy = "no-referrer";
    karte.className = "karte-einbettung";
    rahmen.replaceChildren(karte);
  });
})();

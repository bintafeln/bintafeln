// Aufnahme-Assistent, Schritt „Angehörige“: Leere Zeilen (data-leere-zeile) werden ausgeblendet,
// damit nur die tatsächlich eingetragenen Personen zu sehen sind. Der Knopf [data-zeile-dazu]
// blendet je Klick die nächste leere Zeile ein. Ohne JavaScript bleiben alle Zeilen sichtbar.
(function () {
  "use strict";
  var knopf = document.querySelector("[data-zeile-dazu]");
  if (!knopf) return;
  var leere = Array.prototype.slice.call(document.querySelectorAll("tr[data-leere-zeile]"));
  var hinweis = document.querySelector("[data-keine-personen]");
  var tabelle = leere.length ? leere[0].closest(".tabelle-rahmen") : null;
  leere.forEach(function (zeile) { zeile.hidden = true; });
  function stand() {
    var versteckt = leere.filter(function (zeile) { return zeile.hidden; });
    knopf.hidden = versteckt.length === 0;
    // Ist gar keine Person eingetragen, die ganze (leere) Tabelle ausblenden
    var sichtbar = tabelle ? tabelle.querySelectorAll("tbody tr:not([hidden])").length : 1;
    if (tabelle) tabelle.hidden = sichtbar === 0;
    if (hinweis) hinweis.hidden = sichtbar !== 0;
  }
  knopf.addEventListener("click", function () {
    var naechste = leere.filter(function (zeile) { return zeile.hidden; })[0];
    if (!naechste) return;
    naechste.hidden = false;
    stand();
    var feld = naechste.querySelector("input[type=text]");
    if (feld) feld.focus();
  });
  stand();
})();

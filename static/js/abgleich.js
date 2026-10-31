// Abgleich mit dem Kundenstamm: Regler blendet Treffer unter der gewählten Übereinstimmung aus
// (ADR 0028). Ohne JavaScript bleiben alle Treffer sichtbar.
(function () {
  "use strict";
  var regler = document.querySelector("[data-abgleich-regler] input[type=range]");
  if (!regler) return;
  var wert = document.getElementById("min-score-wert");
  var zahl = document.querySelector("[data-abgleich-zahl]");
  var leer = document.querySelector("[data-abgleich-leer]");
  var bloecke = Array.prototype.slice.call(document.querySelectorAll("[data-antrag-block]"));

  function anwenden() {
    var schwelle = parseInt(regler.value, 10);
    if (wert) wert.textContent = schwelle;
    var sichtbareBloecke = 0;
    bloecke.forEach(function (block) {
      var sichtbar = 0;
      block.querySelectorAll("[data-punkte]").forEach(function (li) {
        var treffer = parseInt(li.getAttribute("data-punkte"), 10) >= schwelle;
        li.hidden = !treffer;
        if (treffer) sichtbar += 1;
      });
      block.hidden = sichtbar === 0;
      if (sichtbar) sichtbareBloecke += 1;
    });
    if (zahl) {
      zahl.textContent =
        sichtbareBloecke === 1 ? "1 Antrag mit Treffer" : sichtbareBloecke + " Anträge mit Treffern";
    }
    if (leer) leer.hidden = sichtbareBloecke !== 0;
  }

  regler.addEventListener("input", anwenden);
  anwenden();
})();

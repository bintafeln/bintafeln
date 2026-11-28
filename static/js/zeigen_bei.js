// Felder nur zeigen, wenn ein anderes Feld desselben Formulars passt:
// <div data-zeigen-bei="quelle=adressen spender"> erscheint nur bei quelle „adressen“ oder
// „spender“. Bei mehreren Häkchen desselben Namens genügt eines davon. Ohne JavaScript bleibt
// alles sichtbar. Genauso macht
// <div data-pflicht-bei="wahl=verlaengern"> die Eingabefelder darin zur Pflicht (sonst nicht).
(function () {
  "use strict";
  function verbinden(block, regel, anwenden) {
    var teile = regel.split("=");
    var formular = block.closest("form");
    if (!formular || teile.length !== 2) return;
    var werte = teile[1].split(" ");
    var felder = formular.querySelectorAll('[name="' + teile[0] + '"]');
    function passt() {
      for (var i = 0; i < felder.length; i++) {
        var f = felder[i];
        var gilt = (f.type !== "radio" && f.type !== "checkbox") || f.checked;
        if (gilt && werte.indexOf(f.value) >= 0) return true;
      }
      return false;
    }
    function pruefen() { anwenden(passt()); }
    felder.forEach(function (f) { f.addEventListener("change", pruefen); });
    pruefen();
  }
  document.querySelectorAll("[data-zeigen-bei]").forEach(function (block) {
    verbinden(block, block.dataset.zeigenBei, function (passt) { block.hidden = !passt; });
  });
  document.querySelectorAll("[data-pflicht-bei]").forEach(function (block) {
    // Ohne das unsichtbare Kalender-Feld von datum.js: Pflicht ist nur das sichtbare Datumsfeld
    var eingaben = block.querySelectorAll("input:not(.datum-pick), textarea, select");
    verbinden(block, block.dataset.pflichtBei, function (passt) {
      block.classList.toggle("pflicht", passt);
      eingaben.forEach(function (e) { e.required = passt; });
    });
  });
})();

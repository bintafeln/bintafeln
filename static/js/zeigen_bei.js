// Felder nur zeigen, wenn ein anderes Feld desselben Formulars passt:
// <div data-zeigen-bei="quelle=adressen spender"> erscheint nur bei quelle „adressen“ oder
// „spender“. Ohne JavaScript bleibt alles sichtbar. Genauso macht
// <div data-pflicht-bei="wahl=verlaengern"> die Eingabefelder darin zur Pflicht (sonst nicht).
(function () {
  "use strict";
  function verbinden(block, regel, anwenden) {
    var teile = regel.split("=");
    var formular = block.closest("form");
    if (!formular || teile.length !== 2) return;
    var werte = teile[1].split(" ");
    var felder = formular.querySelectorAll('[name="' + teile[0] + '"]');
    function wert() {
      for (var i = 0; i < felder.length; i++) {
        var f = felder[i];
        if ((f.type !== "radio" && f.type !== "checkbox") || f.checked) return f.value;
      }
      return "";
    }
    function pruefen() { anwenden(werte.indexOf(wert()) >= 0); }
    felder.forEach(function (f) { f.addEventListener("change", pruefen); });
    pruefen();
  }
  document.querySelectorAll("[data-zeigen-bei]").forEach(function (block) {
    verbinden(block, block.dataset.zeigenBei, function (passt) { block.hidden = !passt; });
  });
  document.querySelectorAll("[data-pflicht-bei]").forEach(function (block) {
    var eingaben = block.querySelectorAll("input, textarea, select");
    verbinden(block, block.dataset.pflichtBei, function (passt) {
      block.classList.toggle("pflicht", passt);
      eingaben.forEach(function (e) { e.required = passt; });
    });
  });
})();

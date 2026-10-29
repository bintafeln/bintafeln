// Felder nur zeigen, wenn ein anderes Feld desselben Formulars passt:
// <div data-zeigen-bei="quelle=adressen spender"> erscheint nur bei quelle „adressen“ oder
// „spender“. Ohne JavaScript bleibt alles sichtbar.
(function () {
  "use strict";
  document.querySelectorAll("[data-zeigen-bei]").forEach(function (block) {
    var teile = block.dataset.zeigenBei.split("=");
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
    function pruefen() { block.hidden = werte.indexOf(wert()) < 0; }
    felder.forEach(function (f) { f.addEventListener("change", pruefen); });
    pruefen();
  });
})();

// „Nach oben“-Knopf unten rechts: erscheint auf jeder Seite, sobald man ein Stück nach unten
// gescrollt hat (nützlich vor allem bei langen Listen), und springt beim Klick an den Seitenanfang.
// Ohne JavaScript bleibt der Knopf verborgen.
(function () {
  "use strict";
  var knopf = document.getElementById("nach-oben");
  if (!knopf) return;
  var SCHWELLE = 400; // px, ab hier erscheint der Knopf

  function pruefen() {
    var y = window.scrollY || document.documentElement.scrollTop || 0;
    knopf.hidden = y < SCHWELLE;
  }

  knopf.addEventListener("click", function () {
    var ruhig = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    window.scrollTo({ top: 0, behavior: ruhig ? "auto" : "smooth" });
  });
  window.addEventListener("scroll", pruefen, { passive: true });
  pruefen();
})();

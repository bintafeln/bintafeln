// Knöpfe mit data-kopieren="<id>" kopieren den Wert dieses Feldes in die Zwischenablage (z. B. die
// Adresse eines Kunden, um sie in einer Karte der Ausgabestellen einzufügen).
(function () {
  "use strict";
  document.addEventListener("click", function (e) {
    var knopf = e.target.closest && e.target.closest("[data-kopieren]");
    if (!knopf) return;
    var feld = document.getElementById(knopf.dataset.kopieren);
    if (!feld) return;
    var text = feld.value || feld.textContent || "";
    var aufschrift = knopf.textContent;
    function fertig() {
      knopf.textContent = "✓ Kopiert";
      window.setTimeout(function () { knopf.textContent = aufschrift; }, 1500);
    }
    if (navigator.clipboard && window.isSecureContext) {
      navigator.clipboard.writeText(text).then(fertig, function () { feld.select(); });
    } else { // ohne HTTPS (Entwicklung): markieren, dann reicht Strg+C
      feld.focus();
      feld.select();
      try { if (document.execCommand("copy")) fertig(); } catch (f) { /* nur markiert */ }
    }
  });
})();

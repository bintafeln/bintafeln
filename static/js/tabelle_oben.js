// Zweiter Scrollbalken oben über breiten Tabellen (.tabelle-rahmen.oben-scrollen), synchron mit
// dem eigentlichen Rahmen. So kann man eine breite Liste seitlich schieben, ohne erst ganz nach
// unten zum normalen Balken zu müssen. Ist die Tabelle nicht breiter als der Platz, bleibt der
// Balken unsichtbar. Läuft auch nach htmx-Nachladen (z. B. Live-Suche) erneut.
(function () {
  "use strict";
  function einbauen(rahmen) {
    if (rahmen.previousElementSibling &&
        rahmen.previousElementSibling.classList.contains("tabelle-oben-scroll")) return;
    var tabelle = rahmen.querySelector("table");
    if (!tabelle) return;
    var oben = document.createElement("div");
    oben.className = "tabelle-oben-scroll";
    oben.setAttribute("aria-hidden", "true");
    var innen = document.createElement("div");
    oben.appendChild(innen);
    rahmen.parentNode.insertBefore(oben, rahmen);

    function breite() { innen.style.width = tabelle.scrollWidth + "px"; }
    breite();
    if (window.ResizeObserver) new ResizeObserver(breite).observe(tabelle);
    window.addEventListener("resize", breite);

    // Beide Balken aneinander koppeln, ohne sich gegenseitig endlos anzustoßen.
    var quelle = null;
    function koppeln(von, nach) {
      von.addEventListener("scroll", function () {
        if (quelle && quelle !== von) return;
        quelle = von;
        nach.scrollLeft = von.scrollLeft;
        window.requestAnimationFrame(function () { quelle = null; });
      });
    }
    koppeln(oben, rahmen);
    koppeln(rahmen, oben);
  }

  function alle() {
    document.querySelectorAll(".tabelle-rahmen.oben-scrollen").forEach(einbauen);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", alle);
  } else {
    alle();
  }
  document.body.addEventListener("htmx:afterSwap", alle);
})();

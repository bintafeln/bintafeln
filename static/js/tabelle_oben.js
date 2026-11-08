// Zweiter Scrollbalken oben über breiten Listen, synchron mit dem eigentlichen Rahmen
// (.tabelle-rahmen). So kann man eine breite Liste seitlich schieben, ohne erst ganz nach unten
// zum normalen Balken zu müssen. Gilt für alle Listen; der obere Balken erscheint nur, wenn die
// Tabelle wirklich breiter ist als der Platz. Läuft auch nach htmx-Nachladen (z. B. Live-Suche).
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
    oben.hidden = true;
    var innen = document.createElement("div");
    oben.appendChild(innen);
    rahmen.parentNode.insertBefore(oben, rahmen);

    function anpassen() {
      innen.style.width = tabelle.scrollWidth + "px";
      // Nur zeigen, wenn die Tabelle breiter ist als der sichtbare Bereich (sonst kein Nutzen).
      oben.hidden = tabelle.scrollWidth <= rahmen.clientWidth + 1;
    }
    anpassen();
    if (window.ResizeObserver) {
      var ro = new ResizeObserver(anpassen);
      ro.observe(tabelle);
      ro.observe(rahmen);
    }
    window.addEventListener("resize", anpassen);

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
    document.querySelectorAll(".tabelle-rahmen").forEach(einbauen);
  }
  if (document.readyState === "loading") {
    document.addEventListener("DOMContentLoaded", alle);
  } else {
    alle();
  }
  document.body.addEventListener("htmx:afterSwap", alle);
})();

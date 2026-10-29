// Mehrere Hintergrundbilder: alle paar Sekunden (Tafel-Einstellungen) langsam zum nächsten
// überblenden. Beim nächsten Seitenaufruf geht es mit dem nächsten Bild weiter (je Bereich im
// sessionStorage gemerkt). Ohne JavaScript bleibt das erste Bild stehen.
(function () {
  "use strict";
  var erstes = document.querySelector(".hintergrund[data-bilder]");
  if (!erstes) return;
  var bilder = erstes.dataset.bilder.split(" ").filter(Boolean);
  if (bilder.length < 2) return;
  var sekunden = Math.max(10, parseInt(erstes.dataset.sekunden, 10) || 60);
  var deckkraft = erstes.style.opacity || "1";
  var schluessel = "bintafeln-hintergrund-" + (erstes.dataset.bereich || "seiten");
  var ruhig = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  var aktuell = erstes;
  var nr = 0;

  function merken() {
    try { sessionStorage.setItem(schluessel, String(nr)); } catch (e) { /* ohne Speicher */ }
  }

  function zeigen(n) {
    var vorlade = new Image();
    vorlade.onload = function () {
      var neu = aktuell.cloneNode(false);
      neu.style.backgroundImage = "url('" + bilder[n] + "')";
      neu.style.opacity = "0";
      neu.style.transition = ruhig ? "none" : "opacity 2.5s ease";
      aktuell.after(neu);
      var alt = aktuell;
      aktuell = neu;
      requestAnimationFrame(function () {
        requestAnimationFrame(function () { neu.style.opacity = deckkraft; });
      });
      setTimeout(function () { alt.remove(); }, ruhig ? 0 : 2600);
    };
    vorlade.src = bilder[n];
  }

  try {
    var gemerkt = parseInt(sessionStorage.getItem(schluessel), 10);
    if (gemerkt >= 0) nr = (gemerkt + 1) % bilder.length;
  } catch (e) { /* ohne Speicher: beim ersten Bild beginnen */ }
  if (nr !== 0) zeigen(nr);
  merken();
  setInterval(function () {
    nr = (nr + 1) % bilder.length;
    zeigen(nr);
    merken();
  }, sekunden * 1000);
})();

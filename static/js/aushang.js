// Aushang-Monitor (ADR 0080): zeigt die Seiten nacheinander (oder je zwei nebeneinander), passt
// die Schrift so an, dass jede Seite ohne Scrollen auf den Bildschirm passt, und holt jede Minute
// den neuen Stand. Ist der Link nicht mehr gültig (neuer Link erzeugt, Aushang aus), verschwinden
// die Namen sofort vom Bildschirm.
(function () {
  "use strict";

  var NEU_LADEN = 60 * 1000;
  var GANZ_NEU = 6 * 60 * 60 * 1000; // neue Programmversion: Seite ganz neu laden
  var body = document.body;
  var gleichzeitig = body.dataset.nebeneinander === "2" ? 2 : 1;
  var dauer = Math.max(5, parseInt(body.dataset.sekunden, 10) || 20) * 1000;
  var start = 0;

  function folien() {
    return Array.prototype.slice.call(document.querySelectorAll("#aushang-folien > .aushang-folie"));
  }

  // Größte Schrift, bei der der Inhalt noch ganz hineinpasst (Suche zwischen 6 und 60 Pixel)
  function einpassen(folie) {
    var inhalt = folie.querySelector(".aushang-inhalt");
    if (!inhalt) return;
    var klein = 6, gross = 60;
    for (var i = 0; i < 12; i++) {
      var mitte = (klein + gross) / 2;
      inhalt.style.fontSize = mitte + "px";
      var passt = inhalt.scrollHeight <= inhalt.clientHeight + 1 &&
        inhalt.scrollWidth <= inhalt.clientWidth + 1;
      if (passt) klein = mitte; else gross = mitte;
    }
    inhalt.style.fontSize = (klein * 0.98) + "px"; // etwas Luft für Rundungen
  }

  function zeigen() {
    var alle = folien();
    if (!alle.length) return;
    start = start % alle.length;
    var sichtbar = [];
    for (var i = 0; i < Math.min(gleichzeitig, alle.length); i++) sichtbar.push((start + i) % alle.length);
    alle.forEach(function (f, nr) { f.classList.toggle("sichtbar", sichtbar.indexOf(nr) >= 0); });
    sichtbar.forEach(function (nr) { einpassen(alle[nr]); });
    var punkte = document.getElementById("aushang-punkte");
    punkte.innerHTML = "";
    if (alle.length > gleichzeitig) {
      alle.forEach(function (_, nr) {
        var p = document.createElement("span");
        p.className = "aushang-punkt" + (sichtbar.indexOf(nr) >= 0 ? " aktiv" : "");
        punkte.appendChild(p);
      });
    }
  }

  function weiter() {
    if (folien().length > gleichzeitig) {
      start += gleichzeitig;
      zeigen();
    }
  }

  function neuLaden() {
    fetch(window.location.href, { cache: "no-store", credentials: "same-origin",
                                  headers: { "X-Aushang": "1" } })
      .then(function (antwort) {
        if (antwort.status === 204) {
          document.getElementById("aushang-folien").innerHTML =
            '<section class="aushang-folie sichtbar aushang-leer"><h1>Dieser Link ist nicht mehr gültig.</h1></section>';
          document.getElementById("aushang-punkte").innerHTML = "";
          return null;
        }
        return antwort.ok ? antwort.text() : null;
      })
      .then(function (html) {
        if (!html) return;
        var neu = new DOMParser().parseFromString(html, "text/html");
        var inhalt = neu.getElementById("aushang-folien");
        if (!inhalt) return;
        document.getElementById("aushang-folien").innerHTML = inhalt.innerHTML;
        document.querySelector(".aushang-kopf").innerHTML = neu.querySelector(".aushang-kopf").innerHTML;
        vollbildKnopf();
        zeigen();
      })
      .catch(function () { /* Netz kurz weg: alter Stand bleibt stehen, nächster Versuch in einer Minute */ });
  }

  function vollbildKnopf() {
    var knopf = document.getElementById("aushang-vollbild");
    if (!knopf || !document.fullscreenEnabled) return;
    knopf.hidden = !!document.fullscreenElement;
    knopf.onclick = function () { document.documentElement.requestFullscreen().catch(function () {}); };
  }

  // Mauszeiger nach kurzer Zeit ausblenden
  var ruhe = null;
  document.addEventListener("mousemove", function () {
    body.classList.remove("aushang-ruhig");
    clearTimeout(ruhe);
    ruhe = setTimeout(function () { body.classList.add("aushang-ruhig"); }, 3000);
  });

  document.addEventListener("fullscreenchange", vollbildKnopf);
  window.addEventListener("resize", zeigen);
  vollbildKnopf();
  zeigen();
  // Schriften laden manchmal erst nach dem ersten Einpassen und ändern die Maße
  if (document.fonts && document.fonts.ready) document.fonts.ready.then(zeigen);
  setInterval(weiter, dauer);
  setInterval(neuLaden, NEU_LADEN);
  setTimeout(function () { window.location.reload(); }, GANZ_NEU);
})();

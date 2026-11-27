// Aufgerufene Nummern auf der Homepage der Tafel (ADR 0181): lädt nur den Kasten regelmäßig neu
// und zählt bis zur nächsten Ausgabe herunter (Tage, Stunden, Minuten – ohne Sekunden).
(function () {
  "use strict";
  var kasten = document.getElementById("stand");
  if (!kasten) return;
  var sekunden = parseInt(kasten.getAttribute("data-neu-laden"), 10) || 10;

  // Gleicher Text wie homepage.countdown() im Server
  function text(ziel) {
    var minuten = Math.floor((ziel - Date.now()) / 60000);
    if (minuten < 1) return "gleich geht es los";
    var tage = Math.floor(minuten / 1440);
    var stunden = Math.floor((minuten % 1440) / 60);
    var teile = [];
    if (tage) teile.push(tage === 1 ? "1 Tag" : tage + " Tage");
    if (tage || stunden) teile.push(stunden + " Std.");
    teile.push((minuten % 60) + " Min.");
    return "noch " + teile.join(", ");
  }

  function zaehlen() {
    var feld = kasten.querySelector("[data-ziel]");
    if (!feld) return;
    var ziel = Date.parse(feld.getAttribute("data-ziel"));
    if (!isNaN(ziel)) feld.textContent = text(ziel);
  }

  function laden() {
    if (document.hidden) return;
    fetch(window.location.pathname + "?teil=1", { credentials: "omit", cache: "no-store" })
      .then(function (antwort) { return antwort.ok ? antwort.text() : null; })
      .then(function (html) { if (html !== null) { kasten.innerHTML = html; zaehlen(); } })
      .catch(function () { /* beim nächsten Mal wieder versuchen */ });
  }

  zaehlen();
  setInterval(laden, sekunden * 1000);
  setInterval(zaehlen, 15000);
  document.addEventListener("visibilitychange", laden);
})();

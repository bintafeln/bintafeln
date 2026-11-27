// Aufgerufene Nummern auf der Homepage der Tafel (ADR 0181): lädt nur den Kasten regelmäßig neu.
(function () {
  "use strict";
  var kasten = document.getElementById("stand");
  if (!kasten) return;
  var sekunden = parseInt(kasten.getAttribute("data-neu-laden"), 10) || 10;

  function laden() {
    if (document.hidden) return;
    fetch(window.location.pathname + "?teil=1", { credentials: "omit", cache: "no-store" })
      .then(function (antwort) { return antwort.ok ? antwort.text() : null; })
      .then(function (html) { if (html !== null) kasten.innerHTML = html; })
      .catch(function () { /* beim nächsten Mal wieder versuchen */ });
  }

  setInterval(laden, sekunden * 1000);
  document.addEventListener("visibilitychange", laden);
})();

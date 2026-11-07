// Merkt am Konto, ob die Kapazitätsübersicht der Warteliste auf- oder zugeklappt ist.
// Der Aufklapper <details data-ansicht-url="…"> schickt beim Umschalten still (POST,
// kapazitaet_zu=0/1) an diese Adresse; der CSRF-Token wird aus einem Formular der Seite gelesen.
// Ohne JavaScript bleibt der serverseitig gerenderte Zustand erhalten, nur das Merken entfällt.
(function () {
  "use strict";
  var auf = document.querySelector("details.kapazitaet-karte[data-ansicht-url]");
  if (!auf) return;
  var token = document.querySelector("input[name=csrfmiddlewaretoken]");
  auf.addEventListener("toggle", function () {
    if (!token) return;
    var daten = new FormData();
    daten.append("csrfmiddlewaretoken", token.value);
    daten.append("kapazitaet_zu", auf.open ? "0" : "1");
    fetch(auf.dataset.ansichtUrl, { method: "POST", body: daten, credentials: "same-origin" });
  });
})();

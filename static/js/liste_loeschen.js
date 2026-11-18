// Listen mit Auswahlkästchen: „Angehakte löschen“ schickt die angehakten Zeilen (Kästchen
// name="id", gehören zum Auswahl-Formular) mit dem Lösch-Formular ab – nach Rückfrage.
// Das Formular trägt data-liste-loeschen und die Wörter: data-eins="Notiz" data-viele="Notizen".
// Für andere Sammelaktionen dieselbe Mechanik: data-tun="in Notizen umwandeln" (statt „löschen“),
// data-wofuer="umgewandelt werden sollen" und data-hinweis="…" (statt des Satzes zum Papierkorb).
(function () {
  "use strict";
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (!form.hasAttribute || !form.hasAttribute("data-liste-loeschen")) return;
    var eins = form.dataset.eins || "Eintrag";
    var viele = form.dataset.viele || "Einträge";
    var gewaehlt = Array.prototype.filter.call(
      document.querySelectorAll('input[type="checkbox"][name="id"]'),
      function (k) { return k.checked; }
    );
    if (!gewaehlt.length) {
      e.preventDefault();
      window.alert("Bitte zuerst die " + viele + " anhaken, die " +
        (form.dataset.wofuer || "gelöscht werden sollen") + ".");
      return;
    }
    var tun = form.dataset.tun || "löschen";
    var frage = gewaehlt.length === 1 ? "1 " + eins + " " + tun + "?"
      : gewaehlt.length + " " + viele + " " + tun + "?";
    var hinweis = "hinweis" in form.dataset ? form.dataset.hinweis
      : "Gelöschtes liegt danach im Papierkorb.";
    if (!window.confirm(frage + (hinweis ? " " + hinweis : ""))) {
      e.preventDefault();
      return;
    }
    Array.prototype.forEach.call(form.querySelectorAll('input[name="id"]'), function (f) { f.remove(); });
    gewaehlt.forEach(function (k) {
      var feld = document.createElement("input");
      feld.type = "hidden";
      feld.name = "id";
      feld.value = k.value;
      form.appendChild(feld);
    });
  });
})();

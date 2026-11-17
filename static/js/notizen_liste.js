// Liste aller Notizen: „Angehakte löschen“ schickt die in der Liste angehakten Notizen
// (Kästchen name="id", gehören zum Auswahl-Formular) mit dem Lösch-Formular ab – nach Rückfrage.
(function () {
  "use strict";
  document.addEventListener("submit", function (e) {
    var form = e.target;
    if (form.id !== "notizen-loeschen") return;
    var gewaehlt = Array.prototype.filter.call(
      document.querySelectorAll('input[type="checkbox"][name="id"]'),
      function (k) { return k.checked; }
    );
    if (!gewaehlt.length) {
      e.preventDefault();
      window.alert("Bitte zuerst die Notizen anhaken, die gelöscht werden sollen.");
      return;
    }
    var frage = gewaehlt.length === 1 ? "Die angehakte Notiz löschen?"
      : "Die " + gewaehlt.length + " angehakten Notizen löschen?";
    if (!window.confirm(frage + " Sie liegen danach im Papierkorb.")) {
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

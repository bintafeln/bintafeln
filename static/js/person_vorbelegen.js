// Antragsformular: Weitere Personen bekommen Nachname und Staatsangehörigkeit der Hauptperson
// vorbefüllt. Überschreibbar – sobald jemand ein Feld selbst ändert (oder es schon einen Wert
// hat, z. B. nach einem Formularfehler), wird es nicht mehr überschrieben. Ohne JavaScript bleibt
// alles leer und von Hand ausfüllbar.
(function () {
  "use strict";

  function einrichten(hauptId, endung) {
    var haupt = document.getElementById(hauptId);
    if (!haupt) return;
    var felder = Array.prototype.filter.call(
      document.querySelectorAll('[id^="id_p"][id$="' + endung + '"]'),
      function (f) { return /^id_p\d+_/.test(f.id); }  // nur weitere Personen, nicht die Hauptperson
    );
    if (!felder.length) return;
    felder.forEach(function (feld) {
      if (feld.value) feld.dataset.selbst = "1";  // schon ausgefüllt: nicht überschreiben
      feld.addEventListener("input", function () { feld.dataset.selbst = "1"; });
      feld.addEventListener("change", function () { feld.dataset.selbst = "1"; });
    });
    function uebernehmen() {
      felder.forEach(function (feld) {
        if (feld.dataset.selbst) return;
        feld.value = haupt.value;
      });
    }
    haupt.addEventListener("input", uebernehmen);
    haupt.addEventListener("change", uebernehmen);
    uebernehmen();  // falls die Hauptperson schon ausgefüllt ist
  }

  einrichten("id_nachname", "_nachname");
  einrichten("id_staatsangehoerigkeit", "_staatsangehoerigkeit");
})();

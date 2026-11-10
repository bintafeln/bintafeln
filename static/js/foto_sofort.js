// Foto eines Nachweises (ADR 0122): Sobald ein Foto aufgenommen oder gewählt ist, geht das
// Formular von selbst ab – ein eigener Knopf „speichern“ ist nicht nötig. Für weitere Seiten
// tippt man erneut auf das Feld. Ohne JavaScript bleibt der Knopf im <noscript>.
(function () {
  "use strict";
  function einrichten(feld) {
    if (feld.dataset.fotoBereit) return;
    feld.dataset.fotoBereit = "1";
    feld.addEventListener("change", function () {
      if (!feld.files || !feld.files.length) return;
      var meldung = feld.form.querySelector("[data-foto-meldung]");
      if (meldung) meldung.textContent = "Foto wird gespeichert …";
      if (feld.form.requestSubmit) feld.form.requestSubmit();
      else feld.form.submit();
    });
  }
  function alle() {
    Array.prototype.forEach.call(document.querySelectorAll("input[data-foto-sofort]"), einrichten);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", alle);
  else alle();
  document.addEventListener("htmx:afterSwap", alle);
})();

// Felder mit data-fokus-maus bekommen beim Laden den Fokus – aber nur auf Geräten mit Maus
// (pointer: fine, z. B. PC/Laptop). Auf Tablets und Handys (Touch) würde sofort die
// Bildschirmtastatur aufgehen und die Seite verdecken; dort bleibt der Fokus daher aus.
// Der Scanner am Einlass nutzt weiterhin natives autofocus und ist davon nicht betroffen.
(function () {
  "use strict";
  try {
    if (!window.matchMedia || !window.matchMedia("(pointer: fine)").matches) return;
  } catch (fehler) {
    return;
  }
  var feld = document.querySelector("[data-fokus-maus]");
  if (feld) {
    feld.focus();
  }
})();

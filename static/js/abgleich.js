// Aufnahme Schritt 2: „alles aus dem Antrag / aus dem Kundenstamm" setzt alle Wahl-Radios der
// Unterschiede auf einmal. Ohne JavaScript bleibt die Wahl je Zeile möglich.
document.querySelectorAll("[data-alle-wahl]").forEach(function (knopf) {
  knopf.addEventListener("click", function () {
    var wahl = knopf.dataset.alleWahl;
    document.querySelectorAll('input[type=radio][value="' + wahl + '"]').forEach(function (radio) {
      if (radio.name && radio.name.indexOf("wahl_") === 0) {
        radio.checked = true;
      }
    });
  });
});

// Neuer Stopp vom Büro (ADR 0159) oder Nachricht der Fahrdienstleitung (ADR 0168): Die Kopfzeile
// fragt alle 30 Sekunden nach (#tour-heuler).
// Gibt es etwas, das noch niemand aus der Mannschaft bestätigt hat, öffnet sich ein roter
// Brief über der Seite – mit Rütteln, Ton und Vibration – und bleibt, bis jemand „Gesehen“ tippt.
// Hat ein anderer aus der Mannschaft schon bestätigt, schließt er sich von selbst.
(function () {
  "use strict";

  function laut() {
    if (navigator.vibrate) { try { navigator.vibrate([300, 100, 300, 100, 500]); } catch (e) { /* Zugabe */ } }
    var Kontext = window.AudioContext || window.webkitAudioContext;
    if (!Kontext) return;
    try {
      var ctx = new Kontext();
      var jetzt = ctx.currentTime;
      [0, 0.35, 0.7].forEach(function (ab) {
        var osc = ctx.createOscillator();
        var staerke = ctx.createGain();
        osc.type = "triangle";
        osc.frequency.setValueAtTime(520, jetzt + ab);
        osc.frequency.linearRampToValueAtTime(880, jetzt + ab + 0.25);
        staerke.gain.setValueAtTime(0.0001, jetzt + ab);
        staerke.gain.exponentialRampToValueAtTime(0.3, jetzt + ab + 0.04);
        staerke.gain.exponentialRampToValueAtTime(0.0001, jetzt + ab + 0.28);
        osc.connect(staerke).connect(ctx.destination);
        osc.start(jetzt + ab);
        osc.stop(jetzt + ab + 0.3);
      });
      setTimeout(function () { ctx.close(); }, 1500);
    } catch (e) { /* Ton ist Zugabe; manche Browser erlauben ihn erst nach einem Tippen */ }
  }

  function pruefen() {
    var huelle = document.getElementById("tour-heuler");
    if (!huelle) return;
    var vorlage = huelle.querySelector("template.heuler-brief");
    var offen = document.querySelector("dialog.heuler-dialog");
    var schluessel = vorlage ? vorlage.dataset.schluessel : "";
    if (offen && offen.dataset.schluessel === schluessel) return;
    if (offen) { offen.close(); offen.remove(); }
    if (!vorlage) return;
    var dialog = document.createElement("dialog");
    dialog.className = "heuler-dialog";
    dialog.dataset.schluessel = schluessel;
    dialog.setAttribute("aria-label", vorlage.dataset.titel || "Neuer Stopp für Ihre Tour");
    dialog.appendChild(vorlage.content.cloneNode(true));
    // bleibt, bis „Gesehen“ getippt ist – Esc schließt ihn nicht
    dialog.addEventListener("cancel", function (e) { e.preventDefault(); });
    document.body.appendChild(dialog);
    dialog.showModal();
    laut();
  }

  document.addEventListener("htmx:afterSettle", function (e) {
    if (e.target && e.target.id === "tour-heuler") pruefen();
  });
})();

// Post der Verwaltung an die Ausgabestelle (ADR 0142): Kommt neue Post, fliegt eine Eule mit
// dem Brief von der Bildmitte in die Kopfzeile und landet dort (#eulenpost). Auf Wunsch ruft
// sie dazu „Huhu“ (Ton je Gerät abschaltbar). Wichtige Post öffnet zusätzlich einen Hinweis
// über der Seite, bis jemand „Gelesen“ bestätigt. Was schon angekündigt wurde, merkt sich der
// Browser für diese Sitzung, damit die Eule nicht bei jedem Seitenwechsel neu einfliegt.
(function () {
  "use strict";

  var GESEHEN = "bintafeln-eulenpost-gesehen";
  var TON = "bintafeln-eulenton";

  function lesen(schluessel, art) {
    try { return window[art].getItem(schluessel); } catch (e) { return null; }
  }
  function schreiben(schluessel, wert, art) {
    try { window[art].setItem(schluessel, wert); } catch (e) { /* privat: dann eben jedes Mal */ }
  }

  function tonAn() { return lesen(TON, "localStorage") !== "aus"; }

  function huhu() {
    if (!tonAn()) return;
    var Kontext = window.AudioContext || window.webkitAudioContext;
    if (!Kontext) return;
    try {
      var ctx = new Kontext();
      var jetzt = ctx.currentTime;
      [[0, 0.28, 470, 420], [0.42, 0.55, 440, 380]].forEach(function (ruf) {
        var osc = ctx.createOscillator();
        var laut = ctx.createGain();
        osc.type = "sine";
        osc.frequency.setValueAtTime(ruf[2], jetzt + ruf[0]);
        osc.frequency.linearRampToValueAtTime(ruf[3], jetzt + ruf[0] + ruf[1]);
        laut.gain.setValueAtTime(0.0001, jetzt + ruf[0]);
        laut.gain.exponentialRampToValueAtTime(0.25, jetzt + ruf[0] + 0.05);
        laut.gain.exponentialRampToValueAtTime(0.0001, jetzt + ruf[0] + ruf[1]);
        osc.connect(laut).connect(ctx.destination);
        osc.start(jetzt + ruf[0]);
        osc.stop(jetzt + ruf[0] + ruf[1] + 0.05);
      });
      setTimeout(function () { ctx.close(); }, 1500);
    } catch (e) { /* Ton ist Zugabe */ }
  }

  function fliegen(platz, danach) {
    var ziel = platz.querySelector(".eule");
    var ruhig = window.matchMedia && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (!ziel || ruhig || !document.body.animate) { danach(); return; }
    var box = ziel.getBoundingClientRect();
    var flieger = ziel.cloneNode(true);
    flieger.classList.add("eule-flieger");
    var groesse = 120;
    flieger.style.width = flieger.style.height = groesse + "px";
    document.body.appendChild(flieger);
    var startX = window.innerWidth / 2 - groesse / 2;
    var startY = window.innerHeight / 2 - groesse / 2;
    var zielX = box.left + box.width / 2 - groesse / 2;
    var zielY = box.top + box.height / 2 - groesse / 2;
    var skala = box.width / groesse;
    platz.classList.add("eule-wartet");
    var flug = flieger.animate([
      { transform: "translate(" + startX + "px," + (window.innerHeight + 40) + "px) scale(.6) rotate(-8deg)", opacity: 0 },
      { transform: "translate(" + startX + "px," + startY + "px) scale(1.2) rotate(6deg)", opacity: 1, offset: 0.35 },
      { transform: "translate(" + startX + "px," + (startY - 20) + "px) scale(1.2) rotate(-6deg)", offset: 0.55 },
      { transform: "translate(" + zielX + "px," + zielY + "px) scale(" + skala + ") rotate(0deg)", opacity: 1 }
    ], { duration: 2600, easing: "ease-in-out", fill: "forwards" });
    flug.onfinish = function () {
      flieger.remove();
      platz.classList.remove("eule-wartet");
      platz.classList.add("eule-gelandet");
      danach();
    };
  }

  function wichtigZeigen(huelle) {
    var vorlage = huelle.querySelector("template.eulen-wichtig");
    if (!vorlage || document.querySelector("dialog.eulen-dialog")) return;
    var dialog = document.createElement("dialog");
    dialog.className = "eulen-dialog";
    dialog.setAttribute("aria-label", "Wichtige Post der Verwaltung");
    dialog.appendChild(vorlage.content.cloneNode(true));
    var spaeter = dialog.querySelector("[data-spaeter]");
    if (spaeter) spaeter.addEventListener("click", function () { dialog.close(); dialog.remove(); });
    document.body.appendChild(dialog);
    dialog.showModal();
  }

  function pruefen() {
    var huelle = document.getElementById("eulenpost");
    if (!huelle) return;
    var jetzt = (huelle.dataset.schluessel || "").split(",").filter(Boolean);
    var gesehen = (lesen(GESEHEN, "sessionStorage") || "").split(",").filter(Boolean);
    var neu = jetzt.filter(function (s) { return gesehen.indexOf(s) < 0; });
    var platz = huelle.querySelector(".eulen-landeplatz");
    schreiben(GESEHEN, gesehen.concat(neu).join(","), "sessionStorage");
    if (!platz) return;
    if (neu.length) {
      fliegen(platz, function () { huhu(); wichtigZeigen(huelle); });
    } else {
      wichtigZeigen(huelle);
    }
  }

  document.addEventListener("DOMContentLoaded", pruefen);
  document.addEventListener("htmx:afterSettle", function (e) {
    if (e.target && e.target.id === "eulenpost") pruefen();
  });

  // Postfach: Ton auf diesem Gerät an/aus
  document.addEventListener("DOMContentLoaded", function () {
    var knopf = document.querySelector("[data-eulenton]");
    if (!knopf) return;
    function zeigen() { knopf.textContent = tonAn() ? "🔔 Ton auf diesem Gerät: an" : "🔕 Ton auf diesem Gerät: aus"; }
    zeigen();
    knopf.addEventListener("click", function () {
      schreiben(TON, tonAn() ? "aus" : "an", "localStorage");
      zeigen();
      huhu();
    });
  });
})();

// Nach dem Absenden eines Formulars an dieselbe Seite weitermachen, wo man war, statt oben zu
// landen (z. B. Filter, Speichern weiter unten, Fehler am Feld). Ein Knopf oder Formular mit
// data-ziel="<id>" springt stattdessen zu diesem Abschnitt, z. B. zur Vorschau. Formulare, die
// woandershin führen (anderer Pfad, neuer Tab), bleiben unberührt. Meldungen oben schweben dann
// kurz über der Seite, damit man sie trotzdem sieht.
(function () {
  "use strict";
  var SCHLUESSEL = "bintafeln-position";

  document.addEventListener("submit", function (e) {
    if (e.defaultPrevented) return; // htmx, Autosave, abgebrochene Rückfrage
    var formular = e.target;
    var knopf = e.submitter;
    var ziel = (knopf && knopf.dataset.ziel) || formular.dataset.ziel || "";
    var fenster = (knopf && knopf.getAttribute("formtarget")) || formular.getAttribute("target");
    if (fenster && fenster !== "_self") return;
    var adresse = (knopf && knopf.getAttribute("formaction")) || formular.getAttribute("action") || "";
    if (new URL(adresse || location.href, location.href).pathname !== location.pathname && !ziel) return;
    try {
      sessionStorage.setItem(SCHLUESSEL, JSON.stringify({
        pfad: location.pathname, y: window.scrollY, ziel: ziel, zeit: Date.now(),
      }));
    } catch (fehler) { /* ohne Speicher: wie bisher oben */ }
  });

  var stand = null;
  try {
    stand = JSON.parse(sessionStorage.getItem(SCHLUESSEL) || "null");
    sessionStorage.removeItem(SCHLUESSEL);
  } catch (fehler) { return; }
  if (!stand || Date.now() - stand.zeit > 60000 || stand.pfad !== location.pathname || location.hash) return;
  var abschnitt = stand.ziel && document.getElementById(stand.ziel);
  if (abschnitt) abschnitt.scrollIntoView({ block: "start" });
  else if (stand.y > 0) window.scrollTo(0, stand.y);
  else return;
  var meldungen = document.querySelector(".meldungen");
  if (meldungen && meldungen.getBoundingClientRect().bottom < 0) {
    meldungen.classList.add("schwebend");
    setTimeout(function () { meldungen.classList.remove("schwebend"); }, 6000);
  }
})();

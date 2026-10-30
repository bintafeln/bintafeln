// Formulare, deren Ergebnis in einem neuen Fenster erscheinen soll (target bzw. formtarget
// „_blank“, z. B. ein PDF). In der iPad-App vom Home-Bildschirm (ohne Tabs und Zurück-Knopf)
// bliebe ein abgeschicktes Formular sonst im selben Fenster, und man käme nicht mehr zurück; nur
// ein Link öffnet dort ein eigenes Fenster mit „Fertig“.
// - GET: immer als Link mit window.open.
// - POST: nur in der App vom Home-Bildschirm. Das Formular geht mit „_fenster=1“ im Hintergrund
//   an den Server (apps.core.pdf.im_fenster), der einen Link zurückgibt; ein kleiner Dialog bietet
//   ihn als „PDF öffnen“ an (ein Fingertipp, sonst blockiert Safari das Fenster).
(function () {
  "use strict";

  function alsApp() {
    return window.navigator.standalone === true ||
      (window.matchMedia && window.matchMedia("(display-mode: standalone)").matches);
  }

  function anbieten(adresse) {
    var dialog = document.createElement("dialog");
    dialog.className = "fenster-dialog";
    var text = document.createElement("p");
    text.textContent = "Das PDF ist fertig.";
    var oeffnen = document.createElement("a");
    oeffnen.className = "knopf";
    oeffnen.href = adresse;
    oeffnen.target = "_blank";
    oeffnen.rel = "noopener";
    oeffnen.textContent = "PDF öffnen";
    var zu = document.createElement("button");
    zu.type = "button";
    zu.className = "knopf knopf-abbrechen";
    zu.textContent = "Schließen";
    var leiste = document.createElement("p");
    leiste.append(oeffnen, " ", zu);
    dialog.append(text, leiste);
    function schliessen() {
      dialog.close();
      dialog.remove();
    }
    oeffnen.addEventListener("click", function () { setTimeout(schliessen, 0); });
    zu.addEventListener("click", schliessen);
    document.body.appendChild(dialog);
    dialog.showModal();
  }

  document.addEventListener("submit", function (ereignis) {
    var formular = ereignis.target;
    var knopf = ereignis.submitter;
    var ziel = (knopf && knopf.getAttribute("formtarget")) || formular.getAttribute("target");
    var methode = ((knopf && knopf.getAttribute("formmethod")) || formular.getAttribute("method") ||
      "get").toLowerCase();
    if (ziel !== "_blank" || ereignis.defaultPrevented) return;
    if (methode === "post" && !alsApp()) return;
    ereignis.preventDefault();
    var daten = new FormData(formular);
    if (knopf && knopf.name) daten.append(knopf.name, knopf.value);
    var aktion = (knopf && knopf.getAttribute("formaction")) ? knopf.formAction : formular.action;
    if (methode !== "post") {
      var abfrage = new URLSearchParams(daten).toString();
      window.open(aktion.split("?")[0] + (abfrage ? "?" + abfrage : ""), "_blank", "noopener");
      return;
    }
    daten.append("_fenster", "1");
    fetch(aktion, { method: "POST", body: daten, credentials: "same-origin" })
      .then(function (antwort) {
        if (!antwort.ok) throw new Error(antwort.status);
        return antwort.json();
      })
      .then(function (inhalt) { anbieten(inhalt.adresse); })
      .catch(function () { window.alert("Das PDF konnte nicht erstellt werden. Bitte noch einmal versuchen."); });
  });
})();

// Kurzfristige Tour in einer Maske (Modul Touren): Treffer der Stationssuche in die Liste der
// gewählten Stationen übernehmen, dort umsortieren und wieder entfernen. Die Reihenfolge der
// Liste ist die Fahrtreihenfolge; jede Station steckt als verstecktes Feld „stationen“ im Formular.
(function () {
  "use strict";
  var rahmen = document.querySelector("[data-stationswahl]");
  if (!rahmen) { return; }
  var liste = rahmen.querySelector("[data-stationswahl-liste]");
  var leer = rahmen.querySelector("[data-stationswahl-leer]");
  var suche = document.getElementById("station-suche");

  function knopf(zeichen, merkmal, text) {
    var k = document.createElement("button");
    k.type = "button";
    k.className = "knopf knopf-zweitrangig knopf-klein";
    k.setAttribute(merkmal, "");
    k.setAttribute("aria-label", text);
    k.textContent = zeichen;
    return k;
  }

  function stand() {
    if (leer) { leer.hidden = liste.children.length > 0; }
  }

  // Die Routenvorschau (touren/_karte.html) lädt sich bei diesem Ereignis neu
  function geaendert() {
    stand();
    document.body.dispatchEvent(new CustomEvent("stationswahl-geaendert", { bubbles: true }));
  }

  function hinzufuegen(pk, name, ort) {
    if (liste.querySelector('input[name="stationen"][value="' + pk + '"]')) { return; }
    var zeile = document.createElement("li");
    var feld = document.createElement("input");
    feld.type = "hidden";
    feld.name = "stationen";
    feld.value = pk;
    var text = document.createElement("span");
    var stark = document.createElement("strong");
    stark.textContent = name;
    var klein = document.createElement("small");
    klein.className = "leise";
    klein.textContent = ort;
    text.appendChild(stark);
    text.appendChild(document.createElement("br"));
    text.appendChild(klein);
    var knoepfe = document.createElement("span");
    knoepfe.className = "tour-folge";
    knoepfe.appendChild(knopf("↑", "data-station-hoch", name + " früher"));
    knoepfe.appendChild(knopf("↓", "data-station-runter", name + " später"));
    knoepfe.appendChild(knopf("✕", "data-station-weg", name + " entfernen"));
    zeile.appendChild(feld);
    zeile.appendChild(text);
    zeile.appendChild(knoepfe);
    liste.appendChild(zeile);
    geaendert();
  }

  rahmen.addEventListener("click", function (ereignis) {
    var ziel = ereignis.target.closest("button");
    if (!ziel) { return; }
    var zeile = ziel.closest("li");
    if (ziel.hasAttribute("data-station-waehlen")) {
      hinzufuegen(ziel.getAttribute("data-station-waehlen"), ziel.getAttribute("data-station-name"),
        ziel.getAttribute("data-station-ort"));
      if (zeile) { zeile.remove(); }
      if (suche) { suche.focus(); }
    } else if (ziel.hasAttribute("data-station-weg") && zeile) {
      zeile.remove();
      geaendert();
    } else if (ziel.hasAttribute("data-station-hoch") && zeile && zeile.previousElementSibling) {
      liste.insertBefore(zeile, zeile.previousElementSibling);
      geaendert();
    } else if (ziel.hasAttribute("data-station-runter") && zeile && zeile.nextElementSibling) {
      liste.insertBefore(zeile.nextElementSibling, zeile);
      geaendert();
    }
  });

  // Enter im Suchfeld soll suchen, nicht die Tour anlegen
  if (suche) {
    suche.addEventListener("keydown", function (ereignis) {
      if (ereignis.key === "Enter") { ereignis.preventDefault(); }
    });
  }
  stand();
})();

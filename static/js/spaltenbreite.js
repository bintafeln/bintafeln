// Spaltenbreite in Listen per Ziehen einstellen: Am rechten Rand jeder Spaltenüberschrift sitzt
// ein schmaler Griff. Ziehen macht die Spalte schmaler oder breiter; die Breiten merkt sich der
// Browser je Liste (localStorage „bintafeln-breite-…“), bis man sie mit „Spaltenbreiten
// zurücksetzen“ unter der Liste wieder entfernt. Gilt für alle Listen in einem .tabelle-rahmen,
// auch nach htmx-Nachladen (Live-Suche). Auf schmalen Bildschirmen (Karten statt Tabelle) aus.
(function () {
  "use strict";
  var MINDEST = 40;

  function schluessel(tabelle, nummer) {
    return "bintafeln-breite-" + location.pathname + "-" + nummer;
  }
  function lesen(name) {
    try { return JSON.parse(localStorage.getItem(name) || "{}") || {}; } catch (e) { return {}; }
  }
  function schreiben(name, werte) {
    try {
      if (Object.keys(werte).length) localStorage.setItem(name, JSON.stringify(werte));
      else localStorage.removeItem(name);
    } catch (e) { /* ohne Speicher: gilt nur bis zum Neuladen */ }
  }
  function titel(th) {
    // Text der Überschrift ohne den Griff; leere Überschriften (Auswahl, Aktionen) über die Position
    return (th.dataset.breiteName || th.textContent || "").trim();
  }
  function zellen(tabelle, index, anzahl) {
    var liste = [];
    Array.prototype.forEach.call(tabelle.tBodies, function (koerper) {
      Array.prototype.forEach.call(koerper.rows, function (zeile) {
        if (zeile.cells.length === anzahl) liste.push(zeile.cells[index]);
      });
    });
    return liste;
  }
  function setzen(tabelle, th, index, anzahl, breite) {
    [th].concat(zellen(tabelle, index, anzahl)).forEach(function (zelle) {
      if (breite === null) {
        zelle.style.width = zelle.style.minWidth = zelle.style.maxWidth = "";
        zelle.classList.remove("breite-fest");
      } else {
        zelle.style.width = zelle.style.minWidth = zelle.style.maxWidth = breite + "px";
        zelle.classList.add("breite-fest");
      }
    });
  }

  function einbauen(rahmen, nummer) {
    var tabelle = rahmen.querySelector("table.tabelle");
    if (!tabelle || !tabelle.tHead || !tabelle.tHead.rows.length) return;
    if (tabelle.dataset.breiteBereit) return;
    var koepfe = Array.prototype.slice.call(tabelle.tHead.rows[0].cells);
    if (koepfe.length < 3) return;
    tabelle.dataset.breiteBereit = "1";
    var name = schluessel(tabelle, nummer);
    var werte = lesen(name);
    var knopf = null;

    function knopfZeigen() {
      var gibtEs = Object.keys(werte).length > 0;
      if (!knopf && gibtEs) {
        knopf = document.createElement("button");
        knopf.type = "button";
        knopf.className = "knopf knopf-zweitrangig spalten-breite-zurueck";
        knopf.textContent = "Spaltenbreiten zurücksetzen";
        knopf.addEventListener("click", function () {
          werte = {};
          schreiben(name, werte);
          koepfe.forEach(function (th, i) { setzen(tabelle, th, i, koepfe.length, null); });
          knopfZeigen();
        });
        rahmen.parentNode.insertBefore(knopf, rahmen.nextSibling);
      }
      if (knopf) knopf.hidden = !gibtEs;
    }

    koepfe.forEach(function (th, index) {
      th.dataset.breiteName = titel(th) || "spalte-" + index;
      if (getComputedStyle(th).position === "static") th.style.position = "relative";
      var griff = document.createElement("span");
      griff.className = "spalten-griff";
      griff.setAttribute("aria-hidden", "true");
      griff.title = "Ziehen: Spaltenbreite ändern";
      th.appendChild(griff);
      if (werte[th.dataset.breiteName]) {
        setzen(tabelle, th, index, koepfe.length, werte[th.dataset.breiteName]);
      }
      griff.addEventListener("click", function (e) { e.preventDefault(); e.stopPropagation(); });
      griff.addEventListener("pointerdown", function (e) {
        if (window.matchMedia("(max-width: 40rem)").matches) return;
        e.preventDefault();
        e.stopPropagation();
        var startX = e.clientX;
        var start = th.getBoundingClientRect().width;
        var breite = start;
        griff.setPointerCapture(e.pointerId);
        document.body.classList.add("spalte-wird-gezogen");
        function bewegen(ev) {
          breite = Math.max(MINDEST, Math.round(start + ev.clientX - startX));
          setzen(tabelle, th, index, koepfe.length, breite);
        }
        function fertig() {
          griff.removeEventListener("pointermove", bewegen);
          griff.removeEventListener("pointerup", fertig);
          griff.removeEventListener("pointercancel", fertig);
          document.body.classList.remove("spalte-wird-gezogen");
          if (breite !== Math.round(start)) {
            werte[th.dataset.breiteName] = breite;
            schreiben(name, werte);
            knopfZeigen();
          }
        }
        griff.addEventListener("pointermove", bewegen);
        griff.addEventListener("pointerup", fertig);
        griff.addEventListener("pointercancel", fertig);
      });
    });
    knopfZeigen();
  }

  function alle() {
    Array.prototype.forEach.call(document.querySelectorAll(".tabelle-rahmen"), einbauen);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", alle);
  else alle();
  document.addEventListener("htmx:afterSwap", alle);
})();

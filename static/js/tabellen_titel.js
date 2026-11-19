// Listen am Handy: Auf schmalen Bildschirmen zeigt bintafeln jede Tabellenzeile als Karte, und vor
// jedem Wert steht die Spaltenüberschrift (aus data-titel, siehe bintafeln.css). Fehlt data-titel
// an einer Zelle, trägt dieses Skript die Überschrift der Spalte aus dem Tabellenkopf nach – so
// ist jede Liste auch hochkant lesbar, ohne dass jede Vorlage daran denken muss.
(function () {
  "use strict";

  function spalten(tabelle) {
    var kopf = tabelle.tHead && tabelle.tHead.rows[tabelle.tHead.rows.length - 1];
    var titel = [];
    if (!kopf) return titel;
    Array.prototype.forEach.call(kopf.cells, function (zelle) {
      var text = (zelle.textContent || "").replace(/\s+/g, " ").trim();
      for (var i = 0; i < (zelle.colSpan || 1); i++) titel.push(text);
    });
    return titel;
  }

  function beschriften(wurzel) {
    (wurzel || document).querySelectorAll("table.tabelle").forEach(function (tabelle) {
      var titel = spalten(tabelle);
      if (!titel.length) return;
      Array.prototype.forEach.call(tabelle.tBodies, function (koerper) {
        Array.prototype.forEach.call(koerper.rows, function (zeile) {
          var spalte = 0;
          Array.prototype.forEach.call(zeile.cells, function (zelle) {
            var breite = zelle.colSpan || 1;
            if (zelle.tagName === "TD" && breite === 1 && !zelle.hasAttribute("data-titel")) {
              zelle.setAttribute("data-titel", titel[spalte] || "");
            }
            spalte += breite;
          });
        });
      });
    });
  }

  if (document.readyState !== "loading") beschriften();
  else document.addEventListener("DOMContentLoaded", function () { beschriften(); });
  document.addEventListener("htmx:afterSettle", function (e) {
    beschriften(e.target && e.target.parentNode ? e.target.parentNode : document);
  });
})();

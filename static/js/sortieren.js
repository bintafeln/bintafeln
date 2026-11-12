// Tabellen im Browser sortieren: <table data-sortierbar>, im Kopf
// <button type="button" class="sortieren" data-sort="text|zahl">. Ein Klick sortiert die Zeilen
// nach dieser Spalte, der nächste dreht die Richtung. Der Sortierwert steht in data-wert der
// Zelle, sonst gilt ihr Text. Die Reihenfolge im Dokument ändert sich wirklich – Formulare
// schicken Auswahlkästchen also in der Reihenfolge, die man sieht.
(function () {
  function wert(zeile, spalte, art) {
    const zelle = zeile.cells[spalte];
    if (!zelle) return art === "zahl" ? 0 : "";
    const roh = zelle.dataset.wert !== undefined ? zelle.dataset.wert : zelle.textContent.trim();
    return art === "zahl" ? parseFloat(String(roh).replace(",", ".")) || 0 : roh;
  }
  document.addEventListener("click", function (e) {
    const knopf = e.target.closest("button.sortieren[data-sort]");
    if (!knopf) return;
    const kopf = knopf.closest("th");
    const tabelle = knopf.closest("table[data-sortierbar]");
    if (!kopf || !tabelle || !tabelle.tBodies.length) return;
    const art = knopf.dataset.sort;
    const ab = knopf.classList.contains("auf"); // war aufsteigend → jetzt absteigend
    tabelle.querySelectorAll("button.sortieren").forEach(function (k) {
      k.classList.remove("auf", "ab");
      k.closest("th").setAttribute("aria-sort", "none");
    });
    knopf.classList.add(ab ? "ab" : "auf");
    kopf.setAttribute("aria-sort", ab ? "descending" : "ascending");
    const koerper = tabelle.tBodies[0];
    const spalte = kopf.cellIndex;
    const zeilen = Array.from(koerper.rows);
    zeilen.sort(function (a, b) {
      const x = wert(a, spalte, art), y = wert(b, spalte, art);
      const v = art === "zahl" ? x - y : String(x).localeCompare(String(y), "de", { numeric: true, sensitivity: "base" });
      return ab ? -v : v;
    });
    zeilen.forEach(function (z) { koerper.appendChild(z); });
  });
})();

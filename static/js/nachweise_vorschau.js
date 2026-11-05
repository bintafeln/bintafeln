// Vorschau der Nachweise: Ein Foto (Link mit data-bild) öffnet beim Klick groß als Popup über der
// Seite; ein PDF (data-fenster) öffnet in einem kleineren eigenen Fenster. Ohne JavaScript bleibt
// es ein normaler Link, der die Datei in einem neuen Tab öffnet.
(function () {
  "use strict";
  if (window.__nachweisVorschau) return; // nur einmal binden (das Skript kann mehrfach eingebunden sein)
  window.__nachweisVorschau = true;

  var dialog;

  function popup(href, name) {
    if (!dialog) {
      dialog = document.createElement("dialog");
      dialog.className = "nachweis-dialog";
      var bild = document.createElement("img");
      bild.alt = "";
      var leiste = document.createElement("div");
      leiste.className = "nachweis-dialog-leiste";
      var link = document.createElement("a");
      link.target = "_blank";
      link.rel = "noopener";
      link.className = "knopf knopf-zweitrangig";
      link.textContent = "In neuem Fenster öffnen";
      var zu = document.createElement("button");
      zu.type = "button";
      zu.className = "knopf knopf-abbrechen";
      zu.textContent = "Schließen";
      leiste.append(link, zu);
      dialog.append(bild, leiste);
      document.body.appendChild(dialog);
      zu.addEventListener("click", function () { dialog.close(); });
      dialog.addEventListener("click", function (e) { if (e.target === dialog) dialog.close(); });
    }
    dialog.querySelector("img").src = href;
    dialog.querySelector("img").alt = name || "";
    dialog.querySelector("a").href = href;
    dialog.showModal();
  }

  document.addEventListener("click", function (e) {
    var a = e.target.closest("a[data-bild], a[data-fenster]");
    if (!a) return;
    e.preventDefault();
    if (a.hasAttribute("data-bild")) {
      popup(a.getAttribute("href"), a.getAttribute("title"));
    } else {
      var w = window.open(a.href, "_blank", "width=900,height=1000,scrollbars=yes,resizable=yes");
      if (!w) window.open(a.href, "_blank"); // falls das Fenster blockiert wurde: normaler Tab
    }
  });
})();

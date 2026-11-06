// Vorschau der Nachweise: Ein Foto (Link mit data-bild) öffnet beim Klick groß als Popup über der
// Seite; ein PDF (data-fenster) öffnet in einem kleineren eigenen Fenster. Ohne JavaScript bleibt
// es ein normaler Link, der die Datei in einem neuen Tab öffnet.
(function () {
  "use strict";
  if (window.__nachweisVorschau) return; // nur einmal binden (das Skript kann mehrfach eingebunden sein)
  window.__nachweisVorschau = true;

  var dialog, bescheid;

  // "Ist ein Bescheid" (nur wenn der Auslöser data-bescheid-url hat, z. B. auf der Prüfungsseite):
  // ordnet den Antrag als Amtsdokument ein und bleibt auf der aktuellen Seite (weiter=…).
  function alsBescheid(url) {
    var marke = document.querySelector("input[name=csrfmiddlewaretoken]");
    if (!marke) { window.location.reload(); return; }
    var form = document.createElement("form");
    form.method = "post";
    form.action = url;
    form.innerHTML =
      '<input type="hidden" name="csrfmiddlewaretoken" value="' + marke.value + '">' +
      '<input type="hidden" name="weiter">';
    form.querySelector('input[name=weiter]').value = window.location.pathname + window.location.search;
    document.body.appendChild(form);
    form.submit();
  }

  function popup(href, name, bescheidUrl) {
    if (!dialog) {
      dialog = document.createElement("dialog");
      dialog.className = "nachweis-dialog";
      var bild = document.createElement("img");
      bild.alt = "";
      var leiste = document.createElement("div");
      leiste.className = "nachweis-dialog-leiste";
      bescheid = document.createElement("button");
      bescheid.type = "button";
      bescheid.className = "knopf knopf-zweitrangig";
      bescheid.textContent = "📄 Ist ein Bescheid";
      var link = document.createElement("a");
      link.target = "_blank";
      link.rel = "noopener";
      link.className = "knopf knopf-zweitrangig";
      link.textContent = "In neuem Fenster öffnen";
      var zu = document.createElement("button");
      zu.type = "button";
      zu.className = "knopf knopf-abbrechen";
      zu.textContent = "Schließen";
      leiste.append(bescheid, link, zu);
      dialog.append(bild, leiste);
      document.body.appendChild(dialog);
      zu.addEventListener("click", function () { dialog.close(); });
      dialog.addEventListener("click", function (e) { if (e.target === dialog) dialog.close(); });
      bescheid.addEventListener("click", function () {
        if (bescheid.dataset.url) alsBescheid(bescheid.dataset.url);
      });
    }
    dialog.querySelector("img").src = href;
    dialog.querySelector("img").alt = name || "";
    dialog.querySelector("a").href = href;
    if (bescheidUrl) { bescheid.dataset.url = bescheidUrl; bescheid.hidden = false; }
    else { bescheid.hidden = true; }
    dialog.showModal();
  }

  document.addEventListener("click", function (e) {
    var a = e.target.closest("a[data-bild], a[data-fenster]");
    if (!a) return;
    e.preventDefault();
    if (a.hasAttribute("data-bild")) {
      popup(a.getAttribute("href"), a.getAttribute("title"), a.getAttribute("data-bescheid-url"));
    } else {
      var w = window.open(a.href, "_blank", "width=900,height=1000,scrollbars=yes,resizable=yes");
      if (!w) window.open(a.href, "_blank"); // falls das Fenster blockiert wurde: normaler Tab
    }
  });
})();

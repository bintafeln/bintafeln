// PDFs in der App vom Home-Bildschirm und auf Kiosk-Tablets (ADR 0141): Dort gibt es keine
// Leiste des Browsers. Ein PDF in einem neuen Fenster ließe sich weder drucken noch schließen.
// Deshalb holt dieses Skript das PDF im Hintergrund und zeigt es in einem Fenster über der
// Seite: alle Seiten als Bilder, „Drucken“ (Teilen-Menü des Geräts mit „Drucken“/AirPrint, sonst
// der Druckdialog), „Sichern“, „Per E-Mail“ und „Schließen“. Man bleibt immer auf der Seite.
// Aktiv in der App (display-mode standalone/fullscreen) oder wenn der Server es für das Gerät
// vorgibt (<body data-pdf-fenster="1">, Ausgabestellen-Konten bzw. „Mein Konto“).
(function () {
  "use strict";

  function alsApp() {
    if (window.navigator.standalone === true) return true;
    if (!window.matchMedia) return false;
    return window.matchMedia("(display-mode: standalone)").matches ||
      window.matchMedia("(display-mode: fullscreen)").matches;
  }

  function aktiv() {
    return alsApp() || (document.body && document.body.dataset.pdfFenster === "1");
  }

  function csrf() {
    try { return JSON.parse(document.body.getAttribute("hx-headers") || "{}")["X-CSRFToken"] || ""; }
    catch (e) { return ""; }
  }

  function element(name, klasse, text) {
    var el = document.createElement(name);
    if (klasse) el.className = klasse;
    if (text) el.textContent = text;
    return el;
  }

  function drucken(blob, name) {
    var datei = new File([blob], name, { type: "application/pdf" });
    if (navigator.canShare && navigator.share && navigator.canShare({ files: [datei] })) {
      navigator.share({ files: [datei], title: name }).catch(function () { /* abgebrochen */ });
      return;
    }
    var rahmen = element("iframe", "pdf-druckrahmen");
    rahmen.src = URL.createObjectURL(blob);
    rahmen.onload = function () {
      try { rahmen.contentWindow.focus(); rahmen.contentWindow.print(); }
      catch (e) { window.open(rahmen.src, "_blank"); }
    };
    document.body.appendChild(rahmen);
    setTimeout(function () { rahmen.remove(); }, 60000);
  }

  function zeigen(adresse) {
    var dialog = element("dialog", "pdf-fenster");
    dialog.setAttribute("aria-label", "PDF");
    var kopf = element("div", "pdf-fenster-kopf");
    var titel = element("strong", "", "PDF wird erstellt …");
    var zu = element("button", "knopf knopf-abbrechen", "✕ Schließen");
    zu.type = "button";
    kopf.append(titel, zu);
    var inhalt = element("div", "pdf-fenster-inhalt");
    dialog.append(kopf, inhalt);
    document.body.appendChild(dialog);
    dialog.showModal();
    var blobAdresse = null;
    function schliessen() {
      dialog.close();
      dialog.remove();
      if (blobAdresse) URL.revokeObjectURL(blobAdresse);
    }
    zu.addEventListener("click", schliessen);
    dialog.addEventListener("cancel", function (e) { e.preventDefault(); schliessen(); });

    var blob, name, signatur;
    fetch(adresse, { credentials: "same-origin", headers: { "X-Bintafeln-Pdf": "1" } })
      .then(function (antwort) {
        if (!antwort.ok) throw new Error(antwort.status);
        var art = antwort.headers.get("Content-Type") || "";
        if (art.indexOf("application/pdf") !== 0) {
          // kein PDF (z. B. eine Datei zum Herunterladen): wie ein normaler Link, im selben Fenster
          schliessen();
          window.location.assign(adresse);
          return null;
        }
        name = antwort.headers.get("X-Pdf-Name") || "dokument.pdf";
        signatur = antwort.headers.get("X-Pdf-Signatur") || "";
        return antwort.blob();
      })
      .then(function (daten) {
        if (!daten) return null;
        blob = daten;
        titel.textContent = name;
        var formular = new FormData();
        formular.append("datei", blob, name);
        formular.append("signatur", signatur);
        return fetch(document.body.dataset.pdfVorschau, {
          method: "POST", body: formular, credentials: "same-origin",
          headers: { "X-CSRFToken": csrf() }
        }).then(function (antwort) {
          if (!antwort.ok) throw new Error(antwort.status);
          return antwort.text();
        });
      })
      .then(function (html) {
        if (html === null || html === undefined) return;
        inhalt.innerHTML = html;
        inhalt.querySelector("[data-pdf-drucken]").addEventListener("click", function () {
          drucken(blob, name);
        });
        inhalt.querySelector("[data-pdf-sichern]").addEventListener("click", function () {
          var link = element("a");
          blobAdresse = blobAdresse || URL.createObjectURL(blob);
          link.href = blobAdresse;
          link.download = name;
          document.body.appendChild(link);
          link.click();
          link.remove();
        });
        var mail = inhalt.querySelector("form[data-pdf-mail]");
        if (mail) mail.addEventListener("submit", function (e) {
          e.preventDefault();
          var daten = new FormData(mail);
          daten.append("datei", blob, name);
          daten.append("signatur", signatur);
          daten.append("dateiname", name);
          var ergebnis = mail.querySelector(".pdf-mail-ergebnis");
          ergebnis.textContent = "Wird gesendet …";
          fetch(mail.action, { method: "POST", body: daten, credentials: "same-origin",
                               headers: { "X-CSRFToken": csrf() } })
            .then(function (antwort) { return antwort.text(); })
            .then(function (text) {
              var seite = new DOMParser().parseFromString(text, "text/html");
              ergebnis.textContent = (seite.body.textContent || "").trim();
            })
            .catch(function () { ergebnis.textContent = "Nicht gesendet. Bitte noch einmal versuchen."; });
        });
      })
      .catch(function () {
        titel.textContent = "Das PDF konnte nicht geladen werden.";
        inhalt.textContent = "Bitte schließen und noch einmal versuchen.";
      });
  }

  window.bintafelnPdf = { aktiv: aktiv, zeigen: zeigen };

  // Links mit target="_blank" auf eigene Seiten (PDFs) im Fenster über der Seite öffnen
  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || !aktiv()) return;
    var link = e.target.closest && e.target.closest("a[target=_blank]");
    // data-extern: führt (über eine eigene Adresse) zu einer fremden Seite, kein PDF – wie gewohnt öffnen
    if (!link || link.hasAttribute("download") || link.hasAttribute("data-extern") ||
        link.origin !== window.location.origin) return;
    e.preventDefault();
    zeigen(link.href);
  });
})();

// Editor für eigene HTML-Texte (Antragstexte): Reiter „Gestalten“ mit Knöpfen (fett, Überschrift,
// Liste, Link, Bild, Farbe, Ausrichtung) und „HTML“ mit dem Quelltext. Beide zeigen denselben
// Text; gespeichert wird immer das Textfeld. Vor dem Anzeigen fallen Skripte und Ereignisse weg,
// beim Speichern bereinigt der Server ohnehin (apps.core.html).
(function () {
  "use strict";

  var VERBOTEN = ["SCRIPT", "STYLE", "IFRAME", "OBJECT", "EMBED", "FORM", "INPUT", "BUTTON",
                  "TEXTAREA", "SELECT", "LINK", "META", "BASE"];
  var KNOEPFE = [
    ["bold", "F", "Fett"], ["italic", "K", "Kursiv"], ["underline", "U", "Unterstrichen"],
    ["h2", "Ü", "Überschrift"], ["p", "¶", "Absatz"],
    ["insertUnorderedList", "•", "Aufzählung"], ["insertOrderedList", "1.", "Nummerierung"],
    ["justifyLeft", "⟸", "Linksbündig"], ["justifyCenter", "⟺", "Zentriert"],
    ["justifyRight", "⟹", "Rechtsbündig"],
    ["link", "🔗", "Link"], ["bild", "🖼", "Bild (Adresse)"], ["farbe", "", "Textfarbe"],
    ["removeFormat", "⌫", "Formatierung entfernen"],
  ];

  function sauber(html) {
    var doc = new DOMParser().parseFromString("<body>" + html + "</body>", "text/html");
    doc.body.querySelectorAll("*").forEach(function (el) {
      if (VERBOTEN.indexOf(el.tagName) >= 0) { el.remove(); return; }
      Array.prototype.slice.call(el.attributes).forEach(function (a) {
        var wert = a.value.replace(/\s/g, "").toLowerCase();
        if (a.name.indexOf("on") === 0 || wert.indexOf("javascript:") === 0) el.removeAttribute(a.name);
      });
    });
    return doc.body.innerHTML;
  }

  function hatHtml(text) { return /<[a-zA-Z\/][^>]*>/.test(text); }

  function einrichten(feld) {
    var rahmen = document.createElement("div");
    rahmen.className = "editor";
    var reiter = document.createElement("div");
    reiter.className = "editor-reiter";
    reiter.setAttribute("role", "tablist");
    var leiste = document.createElement("div");
    leiste.className = "editor-leiste";
    var flaeche = document.createElement("div");
    flaeche.className = "editor-flaeche";
    flaeche.contentEditable = "true";
    flaeche.setAttribute("role", "textbox");
    flaeche.setAttribute("aria-multiline", "true");
    flaeche.setAttribute("aria-label", (feld.labels && feld.labels[0] ? feld.labels[0].textContent : "Text") + " gestalten");
    flaeche.dir = feld.dir || "auto";
    var knoepfe = {};
    ["gestalten", "html"].forEach(function (art) {
      var k = document.createElement("button");
      k.type = "button";
      k.textContent = art === "gestalten" ? "Gestalten" : "HTML";
      k.setAttribute("role", "tab");
      k.addEventListener("click", function () { zeigen(art); });
      reiter.appendChild(k);
      knoepfe[art] = k;
    });

    KNOEPFE.forEach(function (b) {
      var k;
      if (b[0] === "farbe") {
        k = document.createElement("input");
        k.type = "color";
        k.value = "#c1121f";
        k.addEventListener("input", function () { befehl("foreColor", k.value); });
      } else {
        k = document.createElement("button");
        k.type = "button";
        k.textContent = b[1];
        k.addEventListener("mousedown", function (e) { e.preventDefault(); }); // Auswahl behalten
        k.addEventListener("click", function () { knopf(b[0]); });
      }
      k.title = b[2];
      k.setAttribute("aria-label", b[2]);
      k.dataset.befehl = b[0];
      leiste.appendChild(k);
    });

    function uebertragen() { feld.value = flaeche.innerHTML; }

    function befehl(name, wert) {
      flaeche.focus();
      document.execCommand("styleWithCSS", false, true);
      document.execCommand(name, false, wert);
      uebertragen();
    }

    function knopf(name) {
      if (name === "h2" || name === "p") return befehl("formatBlock", "<" + name + ">");
      if (name === "link") {
        var url = window.prompt("Adresse des Links (https://…)", "https://");
        if (url && /^(https?:|mailto:|tel:)/i.test(url)) befehl("createLink", url);
        return;
      }
      if (name === "bild") {
        var bild = window.prompt("Adresse des Bildes (https://…)", "https://");
        if (bild && /^https?:/i.test(bild)) befehl("insertImage", bild);
        return;
      }
      befehl(name);
    }

    function zeigen(art) {
      var html = art === "html";
      if (html) uebertragen();
      else flaeche.innerHTML = sauber(feld.value);
      feld.hidden = !html;
      flaeche.hidden = leiste.hidden = html;
      knoepfe.html.setAttribute("aria-selected", html ? "true" : "false");
      knoepfe.gestalten.setAttribute("aria-selected", html ? "false" : "true");
      rahmen.dataset.ansicht = art;
    }

    flaeche.addEventListener("input", uebertragen);
    feld.parentNode.insertBefore(rahmen, feld);
    rahmen.appendChild(reiter);
    rahmen.appendChild(leiste);
    rahmen.appendChild(flaeche);
    rahmen.appendChild(feld);
    if (feld.form) feld.form.addEventListener("submit", function () {
      if (rahmen.dataset.ansicht === "gestalten") uebertragen();
    });
    // Reiner Text ohne HTML (Zeilenumbrüche zählen) bleibt zunächst im HTML-Reiter
    zeigen(!feld.value.trim() || hatHtml(feld.value) ? "gestalten" : "html");
  }

  document.querySelectorAll("textarea[data-editor]").forEach(einrichten);
})();

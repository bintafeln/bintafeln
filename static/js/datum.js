// Datumsfelder: Man kann das Datum einfach als TT.MM.JJJJ eintippen. Zusätzlich hängt dieses Skript
// an jedes Feld einen kleinen 📅-Knopf, der den gewohnten Kalender des Browsers öffnet – wer lieber
// klickt, kann das also weiter tun, muss aber nicht. Ohne JavaScript bleibt das reine Textfeld, in
// das man tippt. Der Server versteht beide Schreibweisen (TT.MM.JJJJ und JJJJ-MM-TT).
// Auch einfache <input type="date"> werden so zum Feld TT.MM.JJJJ (siehe umstellen()).
// Zwei Zusätze, die ein Feld einschalten kann:
//   data-schnell="heute morgen"  → Knöpfe „Heute“ und „Morgen“ unter dem Feld (der Kalender des
//                                   Browsers lässt sich nicht um eigene Knöpfe erweitern)
//   data-nicht-vor="<id>"        → „Bis“-Feld: liegt es vor dem Feld mit dieser id („Von“), springt
//                                   es auf dessen Datum mit
(function () {
  "use strict";

  function ausDeutsch(text) {
    var iso = /^\s*(\d{4})-(\d{2})-(\d{2})\s*$/.exec(text || "");  // auch so getippt
    if (iso) return iso[1] + "-" + iso[2] + "-" + iso[3];
    var m = /^\s*(\d{1,2})\.(\d{1,2})\.(\d{4})\s*$/.exec(text || "");
    if (!m) return "";
    return m[3] + "-" + m[2].padStart(2, "0") + "-" + m[1].padStart(2, "0");
  }
  function nachDeutsch(iso) {
    var m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(iso || "");
    return m ? m[3] + "." + m[2] + "." + m[1] : "";
  }
  function feuere(feld) {
    feld.dispatchEvent(new Event("input", { bubbles: true }));
    feld.dispatchEvent(new Event("change", { bubbles: true }));
  }

  // Textfeld in eine Hülle setzen und 📅-Knopf samt verstecktem Kalender-Feld danebenstellen.
  function ausstatten(feld) {
    if (feld.dataset.datumBereit) return;
    feld.dataset.datumBereit = "1";
    var huelle = document.createElement("span");
    huelle.className = "datum-feld";
    feld.parentNode.insertBefore(huelle, feld);
    huelle.appendChild(feld);
    var knopf = document.createElement("button");
    knopf.type = "button";
    knopf.className = "datum-kalender";
    knopf.tabIndex = -1; // zum Tippen reicht das Textfeld; der Knopf ist nur die Maus-Alternative
    knopf.setAttribute("aria-label", "Kalender öffnen");
    knopf.textContent = "📅";
    var pick = document.createElement("input");
    pick.type = "date";
    pick.className = "datum-pick";
    pick.tabIndex = -1;
    pick.setAttribute("aria-hidden", "true");
    if (feld.dataset.min) pick.min = feld.dataset.min;
    if (feld.dataset.max) pick.max = feld.dataset.max;
    // Das echte Kalender-Feld liegt unsichtbar genau über dem Knopf: Der Fingertipp trifft es
    // direkt, und der Browser öffnet seinen Kalender von selbst. Auf iPad und iPhone öffnet ein
    // Kalender, der nur per Skript angestoßen wird (showPicker), nicht zuverlässig.
    var stelle = document.createElement("span");
    stelle.className = "datum-knopf";
    stelle.appendChild(knopf);
    stelle.appendChild(pick);
    huelle.appendChild(stelle);
    schnellwahl(feld, huelle);
  }

  var SCHNELL = { heute: ["Heute", 0], morgen: ["Morgen", 1] };
  function tag(inTagen) {
    var d = new Date();
    d.setDate(d.getDate() + inTagen);
    return String(d.getDate()).padStart(2, "0") + "." + String(d.getMonth() + 1).padStart(2, "0") +
      "." + d.getFullYear();
  }
  // Knöpfe „Heute“/„Morgen“ unter dem Feld (data-schnell)
  function schnellwahl(feld, huelle) {
    var welche = (feld.dataset.schnell || "").split(/\s+/).filter(function (w) { return SCHNELL[w]; });
    if (!welche.length) return;
    var zeile = document.createElement("span");
    zeile.className = "datum-schnell";
    welche.forEach(function (w) {
      var knopf = document.createElement("button");
      knopf.type = "button";
      knopf.className = "link-knopf";
      knopf.textContent = SCHNELL[w][0];
      knopf.addEventListener("click", function () {
        feld.value = tag(SCHNELL[w][1]);
        feuere(feld);
      });
      zeile.appendChild(knopf);
    });
    huelle.parentNode.insertBefore(zeile, huelle.nextSibling);
  }

  // Einfache Kalenderfelder (<input type="date">) zeigt der Browser in der Schreibweise seiner
  // Sprache an – auf einem englisch eingestellten Gerät also Monat/Tag/Jahr. Deshalb wird jedes
  // solche Feld zum Textfeld TT.MM.JJJJ; das ursprüngliche Feld bleibt versteckt mit demselben
  // Namen und schickt das Datum weiter als JJJJ-MM-TT, der Server merkt also keinen Unterschied.
  function umstellen(alt) {
    if (alt.classList.contains("datum-pick") || alt.dataset.datumBereit) return;
    var feld = document.createElement("input");
    feld.type = "text";
    feld.className = "datum";
    feld.dataset.datum = "";
    feld.placeholder = "TT.MM.JJJJ";
    feld.autocomplete = "off";
    feld.maxLength = 10;
    feld.size = 10;
    feld.inputMode = "numeric";
    if (alt.id) { feld.id = alt.id; alt.removeAttribute("id"); }
    if (alt.required) { feld.required = true; alt.required = false; }
    ["aria-label", "aria-describedby", "title"].forEach(function (a) {
      if (alt.hasAttribute(a)) feld.setAttribute(a, alt.getAttribute(a));
    });
    if (alt.min) feld.dataset.min = alt.min;
    if (alt.max) feld.dataset.max = alt.max;
    ["schnell", "nichtVor"].forEach(function (a) {
      if (alt.dataset[a]) feld.dataset[a] = alt.dataset[a];
    });
    feld.value = nachDeutsch(alt.value);
    alt.dataset.datumBereit = "1";
    alt.parentNode.insertBefore(feld, alt);
    alt.type = "hidden";
    function uebertragen() {
      var text = feld.value.trim();
      var iso = ausDeutsch(text);
      alt.value = iso;
      feld.setCustomValidity(text && !iso ? "Bitte als TT.MM.JJJJ eingeben, z. B. 24.12.2026." : "");
    }
    // Das Feld mit dem Namen meldet die Änderung weiter: Formular-Skripte (sofort anzeigen,
    // Autosave, htmx) achten auf Felder mit Namen.
    feld.addEventListener("input", function () {
      uebertragen();
      alt.dispatchEvent(new Event("input", { bubbles: true }));
    });
    feld.addEventListener("change", function () {
      uebertragen();
      if (!feld.validationMessage) alt.dispatchEvent(new Event("change", { bubbles: true }));
    });
  }

  function los(wurzel) {
    (wurzel || document).querySelectorAll('input[type="date"]').forEach(umstellen);
    (wurzel || document).querySelectorAll("input[data-datum]").forEach(ausstatten);
  }

  // Verhalten über Delegation, damit es auch für später eingefügte Felder gilt (htmx, neue Zeilen).
  function teile(element) {
    var huelle = element.closest(".datum-feld");
    return {
      feld: huelle && huelle.querySelector("input[data-datum]"),
      pick: huelle && huelle.querySelector(".datum-pick"),
    };
  }
  // Vor dem Öffnen das getippte Datum in den Kalender übernehmen
  function abgleichen(pick) {
    var t = teile(pick);
    var iso = t.feld ? ausDeutsch(t.feld.value) : "";
    if (iso) pick.value = iso;
  }
  ["pointerdown", "focusin"].forEach(function (art) {
    document.addEventListener(art, function (e) {
      var pick = e.target.closest && e.target.closest(".datum-pick");
      if (pick) abgleichen(pick);
    });
  });
  document.addEventListener("click", function (e) {
    var ziel = e.target.closest && e.target.closest(".datum-pick, .datum-kalender");
    if (!ziel) return;
    var pick = teile(ziel).pick;
    if (!pick) return;
    abgleichen(pick);
    // Am PC öffnet ein Klick ins Datumsfeld den Kalender nicht von selbst – hier nachhelfen.
    // Wo der Browser ihn schon selbst geöffnet hat (iPad, iPhone), schadet der Aufruf nicht.
    if (typeof pick.showPicker === "function") {
      try {
        pick.showPicker();
      } catch (fehler) {
        /* Der Browser öffnet den Kalender selbst oder gar nicht – nichts weiter zu tun. */
      }
    }
  });
  document.addEventListener("change", function (e) {
    var pick = e.target.closest && e.target.closest(".datum-pick");
    if (!pick) return;
    var huelle = pick.closest(".datum-feld");
    var feld = huelle && huelle.querySelector("input[data-datum]");
    if (feld && pick.value) {
      feld.value = nachDeutsch(pick.value);
      feuere(feld);
    }
  });

  // „Bis“ nie vor „Von“: Wird „Von“ später gesetzt, springt „Bis“ mit (data-nicht-vor am Bis-Feld)
  document.addEventListener("change", function (e) {
    var von = e.target;
    if (!von.matches || !von.matches("input[data-datum]") || !von.id) return;
    var ab = ausDeutsch(von.value);
    if (!ab) return;
    document.querySelectorAll("input[data-datum][data-nicht-vor]").forEach(function (bis) {
      if (bis.dataset.nichtVor !== von.id || bis === von) return;
      var ende = ausDeutsch(bis.value);
      if (ende && ende < ab) {
        bis.value = nachDeutsch(ab);
        feuere(bis);
      }
    });
  });

  if (document.readyState !== "loading") los();
  else document.addEventListener("DOMContentLoaded", function () { los(); });
  document.body &&
    document.body.addEventListener("htmx:afterSwap", function (e) { los(e.target); });
  // Auch Felder, die ein anderes Skript später einfügt (z. B. Dialoge am Aushang-Monitor)
  if (window.MutationObserver) {
    new MutationObserver(function (aenderungen) {
      aenderungen.forEach(function (a) {
        a.addedNodes.forEach(function (n) {
          if (n.nodeType === 1 && n.querySelector && n.querySelector('input[type="date"]:not(.datum-pick)')) los(n);
        });
      });
    }).observe(document.documentElement, { childList: true, subtree: true });
  }
})();

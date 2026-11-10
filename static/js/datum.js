// Datumsfelder: Man kann das Datum einfach als TT.MM.JJJJ eintippen. Zusätzlich hängt dieses Skript
// an jedes Feld einen kleinen 📅-Knopf, der den gewohnten Kalender des Browsers öffnet – wer lieber
// klickt, kann das also weiter tun, muss aber nicht. Ohne JavaScript bleibt das reine Textfeld, in
// das man tippt. Der Server versteht beide Schreibweisen (TT.MM.JJJJ und JJJJ-MM-TT).
(function () {
  "use strict";

  function ausDeutsch(text) {
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
    // Das echte Kalender-Feld liegt unsichtbar genau über dem Knopf: Der Fingertipp trifft es
    // direkt, und der Browser öffnet seinen Kalender von selbst. Auf iPad und iPhone öffnet ein
    // Kalender, der nur per Skript angestoßen wird (showPicker), nicht zuverlässig.
    var stelle = document.createElement("span");
    stelle.className = "datum-knopf";
    stelle.appendChild(knopf);
    stelle.appendChild(pick);
    huelle.appendChild(stelle);
  }

  function los(wurzel) {
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

  if (document.readyState !== "loading") los();
  else document.addEventListener("DOMContentLoaded", function () { los(); });
  document.body &&
    document.body.addEventListener("htmx:afterSwap", function (e) { los(e.target); });
})();

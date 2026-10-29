// Antrag und Kundenstamm: Die Merkzeichen (G, aG, H, B …) erscheinen erst, wenn bei derselben Person
// ein Grad der Behinderung gewählt ist. Ohne JavaScript bleiben sie immer sichtbar.
(function () {
  "use strict";

  function verbinden(gdb, block) {
    function zeigen() {
      var an = parseInt(gdb.value, 10) > 0;
      block.hidden = !an;
      if (!an) block.querySelectorAll("input[type=checkbox]").forEach(function (k) { k.checked = false; });
    }
    gdb.addEventListener("change", zeigen);
    zeigen();
  }

  document.querySelectorAll("[data-merkzeichen-fuer]").forEach(function (block) {
    var gdb = document.getElementById(block.dataset.merkzeichenFuer);
    if (gdb) verbinden(gdb, block);
  });
  // Kundenstamm („Person bearbeiten“): das Auswahlfeld nennt die Merkzeichen selbst
  document.querySelectorAll("select[data-merkzeichen]").forEach(function (gdb) {
    if (document.querySelector('[data-merkzeichen-fuer="' + gdb.id + '"]')) return;
    var liste = document.getElementById(gdb.dataset.merkzeichen);
    if (liste) verbinden(gdb, liste.closest(".feld") || liste);
  });
})();

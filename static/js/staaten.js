// Ergänzt in Auswahllisten der Staatsangehörigkeit die Namen in der Sprache der Seite und
// sortiert danach. Ohne JavaScript oder ohne Intl.DisplayNames bleiben die deutschen Namen.
(function () {
  var sprache = document.documentElement.lang || "de";
  if (sprache === "de" || !window.Intl || !Intl.DisplayNames) return;
  var namen;
  try {
    namen = new Intl.DisplayNames([sprache, "en"], { type: "region" });
  } catch (e) {
    return;
  }
  document.querySelectorAll("select").forEach(function (auswahl) {
    var mitLand = Array.prototype.filter.call(auswahl.options, function (o) {
      return o.dataset.land;
    });
    if (!mitLand.length) return;
    mitLand.forEach(function (o) {
      var eigen = namen.of(o.dataset.land);
      if (eigen && eigen !== o.dataset.land && eigen !== o.text) o.text = eigen + " – " + o.text;
    });
    var danach = mitLand[mitLand.length - 1].nextSibling;
    mitLand.sort(function (a, b) { return a.text.localeCompare(b.text, sprache); });
    mitLand.forEach(function (o) { auswahl.insertBefore(o, danach); });
  });
})();

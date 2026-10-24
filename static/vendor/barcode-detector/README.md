# barcode-detector (mitgeliefert)

Liest Barcodes mit der Kamera, wo der Browser keinen eigenen `BarcodeDetector` hat (z. B. iPhone).
Genutzt von `static/js/kamera_scanner.js`.

- `ponyfill.js`: barcode-detector 3.2.2, `dist/iife/ponyfill.js` (MIT, `LICENSE-barcode-detector`)
- `zxing_reader.wasm`: zxing-wasm 3.1.3, `dist/reader/zxing_reader.wasm` (MIT,
  `LICENSE-zxing-wasm`; enthält zxing-cpp, Apache-2.0)
- SHA-256 der WASM-Datei (prüft die Bibliothek selbst):
  `2ebda08a93eea3efcd8399cda6b276e6a0b1de4fec60b4d8988a047de4c6d1ba`

Aktualisieren: beide Pakete mit `npm pack` in genau zueinander passenden Versionen holen
(`barcode-detector` nennt seine `zxing-wasm`-Version in `package.json`) und beide Dateien
gemeinsam ersetzen.

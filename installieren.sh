#!/usr/bin/env bash
# bintafeln auf einem frischen Server einrichten – ein Befehl von null an (siehe README):
#
#   curl -fsSL https://raw.githubusercontent.com/bintafeln/bintafeln/main/installieren.sh | sudo bash
#
# Das Skript installiert git, lädt bintafeln nach /opt/bintafeln und ruft dort
# "./betrieb installieren" auf (Server prüfen, Docker, .env, starten). Vorhandenes wird nicht
# überschrieben: Gibt es den Ordner schon, geht es dort nur weiter.
#
# Anpassen über Umgebungsvariablen:
#   BINTAFELN_ORDNER   Zielordner (Vorgabe /opt/bintafeln)
#   BINTAFELN_QUELLE   Adresse des Repositorys (Vorgabe: das Repository des Projekts)
#   BINTAFELN_JA=1     ohne Rückfragen (Vorgaben: Entwicklungsmodus ohne Domain, Europe/Berlin)
#
# Alles steht in Funktionen und startet erst in der letzten Zeile: Bricht das Herunterladen
# mittendrin ab, wird kein halbes Skript ausgeführt.
set -euo pipefail

ORDNER="${BINTAFELN_ORDNER:-/opt/bintafeln}"
QUELLE="${BINTAFELN_QUELLE:-https://github.com/bintafeln/bintafeln.git}"

hinweis() { printf '\n==> %s\n' "$*"; }
fehler() { printf 'FEHLER: %s\n' "$*" >&2; exit 1; }

pakete() {
    local fehlt=()
    command -v git >/dev/null 2>&1 || fehlt+=(git)
    command -v curl >/dev/null 2>&1 || fehlt+=(curl)
    command -v openssl >/dev/null 2>&1 || fehlt+=(openssl)
    [[ -e /etc/ssl/certs/ca-certificates.crt ]] || fehlt+=(ca-certificates)
    (( ${#fehlt[@]} )) || return 0
    command -v apt-get >/dev/null 2>&1 \
        || fehler "Es fehlen: ${fehlt[*]}. Bitte installieren und erneut aufrufen (automatisch nur mit apt)."
    hinweis "Fehlende Programme installieren: ${fehlt[*]}"
    apt-get update
    DEBIAN_FRONTEND=noninteractive apt-get install -y "${fehlt[@]}"
}

holen() {
    if [[ -x "$ORDNER/betrieb" ]]; then
        echo "bintafeln liegt schon in $ORDNER – dort geht es weiter (nichts wird überschrieben)."
        return 0
    fi
    if [[ -e "$ORDNER" && -n "$(ls -A "$ORDNER" 2>/dev/null)" ]]; then
        fehler "$ORDNER gibt es schon und ist nicht leer, enthält aber kein bintafeln. Anderen Ordner wählen: BINTAFELN_ORDNER=/pfad"
    fi
    hinweis "bintafeln nach $ORDNER herunterladen"
    git clone "$QUELLE" "$ORDNER" \
        || fehler "Herunterladen von $QUELLE fehlgeschlagen. Internetverbindung prüfen; bei einem privaten Repository zuerst von Hand klonen (README, Schritt 2)."
    # Wer mit sudo aufruft, soll danach ohne sudo im Ordner arbeiten können
    if [[ -n "${SUDO_USER:-}" && "$SUDO_USER" != root ]]; then
        chown -R "$SUDO_USER": "$ORDNER"
    fi
}

main() {
    [[ $EUID -eq 0 ]] || fehler "Bitte mit Root-Rechten aufrufen: … | sudo bash"
    local id=""
    # shellcheck disable=SC1091
    id=$(. /etc/os-release 2>/dev/null && printf '%s' "${ID:-}") || true
    [[ "$id" == debian ]] \
        || echo "Hinweis: Getestet ist Debian 13. Auf anderen Systemen muss Docker ggf. von Hand installiert werden."
    pakete
    holen
    cd "$ORDNER"
    hinweis "Einrichtung starten"
    # Über "curl … | bash" ist die Tastatur nicht die Eingabe: Rückfragen vom Terminal lesen
    if [[ "${BINTAFELN_JA:-}" != 1 && ! -t 0 ]] && (: < /dev/tty) 2>/dev/null; then
        ./betrieb installieren < /dev/tty
    else
        ./betrieb installieren
    fi
}

main "$@"
exit

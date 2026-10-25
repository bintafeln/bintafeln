#!/bin/sh
# Dienst "updater" von bintafeln (ADR 0043): Update aus der Oberfläche.
#
#   updater dienst    Standard: Versionen abrufen, Aufträge aus bintafeln annehmen
#   updater lauf      (intern) ein Update ausführen; läuft in einem eigenen Container
#
# bintafeln selbst bekommt keinen Zugriff auf Docker. Es legt nur die Datei auftrag.txt mit der
# gewünschten Version in den gemeinsamen Ordner /betrieb. Dieser Dienst prüft die Version (nur
# vorhandene Versions-Tags) und startet dafür einen eigenen Container, der im Projektordner
# "./betrieb update VERSION" ausführt (mit Sicherung vorher). Der eigene Container ist nötig,
# weil das Update auch diesen Dienst neu startet.
#
# Dateien in /betrieb (Schlüssel=Wert, liest bintafeln):
#   lebenszeichen.txt  zeit=…                    alle 5 Sekunden
#   versionen.txt      installiert, abgerufen, fehler, je Version eine Zeile version=NAME|DATUM|ÄNDERUNGEN
#   status.txt         zustand (laeuft|ok|fehler), version, beginn, ende, meldung
#   protokoll.txt      Ausgabe des letzten Updates
#   auftrag.txt        von bintafeln: version=…, von=…
#   abrufen.txt        von bintafeln: sofort nach neuen Versionen suchen
set -eu

PROJEKT=/projekt
BETRIEB=/betrieb
VERSIONSMUSTER='^[0-9]{4}\.[0-9]{1,2}\.[0-9]+$'
ABRUF_ALLE=600
# git im Projektordner, der einem anderen Benutzer gehört
export GIT_CONFIG_COUNT=1 GIT_CONFIG_KEY_0=safe.directory GIT_CONFIG_VALUE_0='*'

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*"
}

zeit() {
    date '+%Y-%m-%dT%H:%M:%S%z'
}

# schreiben DATEI: stdin vollständig ersetzen (erst schreiben, dann umbenennen)
schreiben() {
    cat > "$BETRIEB/.$1.tmp"
    chmod 644 "$BETRIEB/.$1.tmp"
    mv "$BETRIEB/.$1.tmp" "$BETRIEB/$1"
}

status_setzen() {
    {
        echo "zustand=$1"
        echo "version=$2"
        echo "beginn=$3"
        echo "ende=$4"
        echo "meldung=$5"
    } | schreiben status.txt
}

status_wert() {
    sed -n "s/^$1=//p" "$BETRIEB/status.txt" 2>/dev/null | head -n 1
}

# Dateien, die git als root anlegt, wieder dem Besitzer des Projektordners geben
besitz_zurueck() {
    besitzer=$(stat -c %u:%g "$1")
    chown -R "$besitzer" "$1/.git"
    [ ! -f "$1/VERSION" ] || chown "$besitzer" "$1/VERSION"
    (cd "$1" && git ls-files -z | xargs -0 chown -h "$besitzer") 2>/dev/null || true
}

# Angaben über den eigenen Container (Docker vergibt den Namen des Rechners = Container-ID)
eigenes() {
    docker inspect -f "$1" "$(hostname)"
}

# Titel der Änderungen in BEREICH (Pull-Request-Titel aus Merge-Commits), getrennt durch Tab
aenderungen() {
    git -C "$PROJEKT" log --first-parent --format='%H' "$1" 2>/dev/null | head -n 15 \
        | while read -r commit; do
            titel=$(git -C "$PROJEKT" log -1 --format='%s' "$commit")
            case "$titel" in
                "Merge pull request"*)
                    titel=$(git -C "$PROJEKT" log -1 --format='%b' "$commit" | sed -n '/./{p;q}')
                    ;;
            esac
            [ -n "$titel" ] && printf '%s\t' "$titel" | tr '|' '/'
        done
}

versionen_abrufen() {
    fehler=""
    if ! ausgabe=$(git -C "$PROJEKT" fetch --quiet --tags --force origin 2>&1); then
        fehler="Neue Versionen konnten nicht abgerufen werden: $(echo "$ausgabe" | head -n 1)"
        log "$fehler"
    fi
    besitz_zurueck "$PROJEKT"
    installiert=$(cat "$PROJEKT/VERSION" 2>/dev/null || true)
    {
        echo "abgerufen=$(zeit)"
        echo "installiert=$installiert"
        echo "fehler=$fehler"
        vorher=""
        for v in $(git -C "$PROJEKT" tag --list | grep -E "$VERSIONSMUSTER" | sort -V | tail -n 20); do
            datum=$(git -C "$PROJEKT" log -1 --format=%cs "$v")
            if [ -n "$vorher" ]; then bereich="$vorher..$v"; else bereich="$v"; fi
            echo "version=$v|$datum|$(aenderungen "$bereich")"
            vorher="$v"
        done
    } | schreiben versionen.txt
}

lauf_name() {
    echo "$(eigenes '{{index .Config.Labels "com.docker.compose.project"}}')-update"
}

lauf_aktiv() {
    [ "$(docker inspect -f '{{.State.Running}}' "$(lauf_name)" 2>/dev/null)" = true ]
}

# Ein Update in einem eigenen Container starten: Projektordner unter demselben Pfad wie auf dem
# Server, damit docker compose dort alle Pfade so auflöst wie bei "./betrieb update" von Hand.
update_starten() {
    version="$1"
    host_pfad=$(eigenes '{{range .Mounts}}{{if eq .Destination "/projekt"}}{{.Source}}{{end}}{{end}}')
    volume=$(eigenes '{{range .Mounts}}{{if eq .Destination "/betrieb"}}{{.Name}}{{end}}{{end}}')
    image=$(eigenes '{{.Config.Image}}')
    docker rm -f "$(lauf_name)" > /dev/null 2>&1 || true
    status_setzen laeuft "$version" "$(zeit)" "" "Update auf $version läuft …"
    : | schreiben protokoll.txt
    docker run -d --name "$(lauf_name)" \
        -v /var/run/docker.sock:/var/run/docker.sock \
        -v "$host_pfad:$host_pfad" -w "$host_pfad" -v "$volume:/betrieb" \
        -e "ZIEL_VERSION=$version" -e "BEGINN=$(zeit)" \
        "$image" lauf > /dev/null
    log "Update auf $version gestartet."
}

auftrag_annehmen() {
    datei="$BETRIEB/auftrag.txt"
    [ -f "$datei" ] || return 0
    version=$(sed -n 's/^version=//p' "$datei" | head -n 1)
    von=$(sed -n 's/^von=//p' "$datei" | head -n 1)
    rm -f "$datei"
    if lauf_aktiv; then
        log "Auftrag für $version verworfen: Es läuft schon ein Update."
        return 0
    fi
    if ! echo "$version" | grep -Eq "$VERSIONSMUSTER" \
        || ! git -C "$PROJEKT" rev-parse --quiet --verify "refs/tags/$version" > /dev/null; then
        status_setzen fehler "$version" "$(zeit)" "$(zeit)" "Die Version $version gibt es nicht."
        return 0
    fi
    log "Update auf $version angefordert von $von."
    update_starten "$version"
}

dienst() {
    mkdir -p "$BETRIEB"
    chmod 777 "$BETRIEB"
    log "Dienst läuft: nimmt Updates aus bintafeln an (Einstellungen → Update)."
    # Ein Update, das bei einem Neustart des Servers abgebrochen wurde
    if [ "$(status_wert zustand)" = laeuft ] && ! lauf_aktiv; then
        status_setzen fehler "$(status_wert version)" "$(status_wert beginn)" "$(zeit)" \
            "Das Update wurde unterbrochen. Bitte erneut starten oder auf dem Server ./betrieb update ausführen."
    fi
    letzter_abruf=0
    while true; do
        echo "zeit=$(zeit)" | schreiben lebenszeichen.txt
        jetzt=$(date +%s)
        if [ -f "$BETRIEB/abrufen.txt" ] || [ $((jetzt - letzter_abruf)) -ge "$ABRUF_ALLE" ]; then
            rm -f "$BETRIEB/abrufen.txt"
            versionen_abrufen || log "Versionen konnten nicht gelesen werden."
            letzter_abruf=$jetzt
        fi
        auftrag_annehmen || log "Auftrag konnte nicht angenommen werden."
        sleep 5
    done
}

# Läuft im eigenen Container im Projektordner (siehe update_starten)
lauf() {
    if BINTAFELN_JA=1 ./betrieb update "$ZIEL_VERSION" > /betrieb/protokoll.txt 2>&1; then
        status_setzen ok "$ZIEL_VERSION" "$BEGINN" "$(zeit)" "Update auf $ZIEL_VERSION abgeschlossen."
    else
        status_setzen fehler "$ZIEL_VERSION" "$BEGINN" "$(zeit)" \
            "Das Update auf $ZIEL_VERSION ist fehlgeschlagen. Details im Protokoll."
    fi
    besitz_zurueck "$(pwd)"
}

case "${1:-dienst}" in
    dienst) dienst ;;
    lauf) lauf ;;
    *) echo "Unbekannter Befehl '$1'." >&2; exit 2 ;;
esac

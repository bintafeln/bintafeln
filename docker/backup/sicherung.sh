#!/bin/sh
# Sicherung von bintafeln: Datenbank und hochgeladene Dateien, verschlüsselt mit age.
#
#   sicherung zeitplan                      tägliche Sicherung (Standard des Dienstes)
#   sicherung jetzt                         sofort sichern
#   sicherung pruefen NAME                  Sicherung mit /schluessel probeweise entschlüsseln
#   sicherung entschluesseln NAME TEIL      TEIL (datenbank|medien) entschlüsselt ausgeben
#   sicherung schluessel                    neues Schlüsselpaar erzeugen
#
# Unverschlüsselte Daten werden nie auf die Platte geschrieben: pg_dump und tar schreiben
# direkt in age.
set -eu
# Die BusyBox-Shell des Images kennt pipefail.
# shellcheck disable=SC3040
set -o pipefail

ZIEL=/sicherungen
MEDIEN=/daten/media
STATUS="$ZIEL/status.txt"
ZEITPLAN_MARKE="$ZIEL/.zeitplan"
PRIVATER_SCHLUESSEL=/schluessel
UHRZEIT="${SICHERUNG_UHRZEIT:-02:30}"
ANZAHL="${SICHERUNG_ANZAHL:-14}"
SCHLUESSEL="${SICHERUNG_SCHLUESSEL:-}"
NAMENSMUSTER='^[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{6}$'

log() {
    echo "$(date '+%Y-%m-%d %H:%M:%S') $*"
}

fehler() {
    log "FEHLER: $*" >&2
    exit 1
}

zeitstempel() {
    date '+%Y-%m-%dT%H:%M:%S%z'
}

status_wert() {
    if [ -f "$STATUS" ]; then
        sed -n "s/^$1=//p" "$STATUS" | head -n 1
    fi
}

# status_schreiben ERGEBNIS MELDUNG [ZEITPUNKT_ERFOLG]
status_schreiben() {
    erfolgreich="${3:-$(status_wert letzte_erfolgreiche)}"
    mkdir -p "$ZIEL"
    {
        echo "letzter_versuch=$(zeitstempel)"
        echo "ergebnis=$1"
        echo "meldung=$2"
        echo "letzte_erfolgreiche=$erfolgreich"
    } > "$STATUS.tmp"
    chmod 644 "$STATUS.tmp"
    mv "$STATUS.tmp" "$STATUS"
}

einstellungen_pruefen() {
    echo "$UHRZEIT" | grep -Eq '^([01][0-9]|2[0-3]):[0-5][0-9]$' \
        || fehler "BINTAFELN_SICHERUNG_UHRZEIT muss die Form HH:MM haben, nicht '$UHRZEIT'."
    echo "$ANZAHL" | grep -Eq '^[1-9][0-9]*$' \
        || fehler "BINTAFELN_SICHERUNG_ANZAHL muss eine Zahl ab 1 sein, nicht '$ANZAHL'."
}

name_pruefen() {
    echo "$1" | grep -Eq "$NAMENSMUSTER" || fehler "Ungültiger Name einer Sicherung: '$1'."
    [ -f "$ZIEL/$1/info.txt" ] || fehler "Sicherung '$1' nicht gefunden oder unvollständig."
}

erstellen() {
    pg_dump --format=custom --no-owner | age -r "$SCHLUESSEL" -o "$1/datenbank.dump.age" \
        || return 1
    mkdir -p "$MEDIEN"
    tar -C "$MEDIEN" -cf - . | age -r "$SCHLUESSEL" -o "$1/medien.tar.age" || return 1
    {
        echo "zeitpunkt=$(zeitstempel)"
        echo "datenbank=$PGDATABASE"
        echo "postgresql=$(pg_dump --version | sed 's/^pg_dump (PostgreSQL) //')"
        echo "groesse_datenbank=$(wc -c < "$1/datenbank.dump.age")"
        echo "groesse_medien=$(wc -c < "$1/medien.tar.age")"
    } > "$1/info.txt" || return 1
}

aufraeumen() {
    find "$ZIEL" -mindepth 1 -maxdepth 1 -type d | sed 's|.*/||' | grep -E "$NAMENSMUSTER" \
        | sort -r | tail -n +"$((ANZAHL + 1))" | while read -r alt; do
            rm -rf "${ZIEL:?}/$alt"
            log "Alte Sicherung $alt gelöscht."
        done || true
}

sichern() {
    if [ -z "$SCHLUESSEL" ]; then
        status_schreiben nicht_eingerichtet "Kein Sicherungsschlüssel in .env eingetragen."
        fehler "Keine Sicherung: BINTAFELN_SICHERUNG_SCHLUESSEL ist nicht gesetzt (./bintafeln schluessel)."
    fi
    case "$SCHLUESSEL" in
        age1*) ;;
        *)
            status_schreiben fehler "Der Sicherungsschlüssel in .env ist ungültig."
            fehler "BINTAFELN_SICHERUNG_SCHLUESSEL muss mit age1 beginnen."
            ;;
    esac

    mkdir -p "$ZIEL"
    find "$ZIEL" -mindepth 1 -maxdepth 1 -name '.*.unvollstaendig' -exec rm -rf {} +
    name="$(date '+%Y-%m-%d_%H%M%S')"
    arbeit="$ZIEL/.$name.unvollstaendig"
    mkdir "$arbeit"
    log "Sicherung $name läuft …"

    if erstellen "$arbeit"; then
        chmod 644 "$arbeit"/*
        chmod 755 "$arbeit"
        mv "$arbeit" "$ZIEL/$name"
        status_schreiben ok "Sicherung $name erstellt." "$(zeitstempel)"
        aufraeumen
        log "Sicherung $name erstellt."
    else
        rm -rf "$arbeit"
        status_schreiben fehler "Die letzte Sicherung ist fehlgeschlagen (Details: docker compose logs backup)."
        fehler "Sicherung $name fehlgeschlagen."
    fi
}

minuten() {
    stunden=$(echo "${1%%:*}" | sed 's/^0*//')
    minuten=$(echo "${1#*:}" | sed 's/^0*//')
    echo $(( ${stunden:-0} * 60 + ${minuten:-0} ))
}

zeitplan() {
    einstellungen_pruefen
    log "Zeitplan aktiv: tägliche Sicherung um $UHRZEIT Uhr, $ANZAHL Stände werden aufbewahrt."
    if [ -z "$SCHLUESSEL" ]; then
        log "Hinweis: Noch kein Sicherungsschlüssel eingetragen. Einrichten mit: ./bintafeln schluessel"
        status_schreiben nicht_eingerichtet "Kein Sicherungsschlüssel in .env eingetragen."
    fi
    ziel=$(minuten "$UHRZEIT")
    while true; do
        heute=$(date +%Y-%m-%d)
        zuletzt=$(cat "$ZEITPLAN_MARKE" 2>/dev/null || true)
        if [ "$(minuten "$(date +%H:%M)")" -ge "$ziel" ] && [ "$zuletzt" != "$heute" ]; then
            echo "$heute" > "$ZEITPLAN_MARKE"
            sichern || true
        fi
        sleep 30
    done
}

entschluesseln() {
    name_pruefen "$1"
    [ -f "$PRIVATER_SCHLUESSEL" ] || fehler "Kein privater Schlüssel unter $PRIVATER_SCHLUESSEL eingebunden."
    case "$2" in
        datenbank) datei="datenbank.dump.age" ;;
        medien) datei="medien.tar.age" ;;
        *) fehler "Unbekannter Teil '$2' (datenbank oder medien)." ;;
    esac
    age -d -i "$PRIVATER_SCHLUESSEL" "$ZIEL/$1/$datei"
}

pruefen() {
    entschluesseln "$1" datenbank | pg_restore --list > /dev/null \
        || fehler "Datenbank-Sicherung lässt sich nicht entschlüsseln oder lesen."
    entschluesseln "$1" medien | tar -tf - > /dev/null \
        || fehler "Datei-Sicherung lässt sich nicht entschlüsseln oder lesen."
    log "Sicherung $1 ist lesbar."
}

case "${1:-zeitplan}" in
    zeitplan) zeitplan ;;
    jetzt) einstellungen_pruefen; sichern ;;
    pruefen) pruefen "${2:-}" ;;
    entschluesseln) entschluesseln "${2:-}" "${3:-}" ;;
    schluessel) age-keygen ;;
    *) fehler "Unbekannter Befehl '$1'." ;;
esac

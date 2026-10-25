#!/bin/sh
# Sicherung von bintafeln: Datenbank und hochgeladene Dateien, verschlüsselt mit age.
#
#   sicherung zeitplan                      Dienst: führt die Sicherungsaufträge aus (Standard)
#   sicherung jetzt                         sofort in den Sicherungsordner sichern
#   sicherung pruefen NAME                  Sicherung mit /schluessel probeweise entschlüsseln
#   sicherung entschluesseln NAME TEIL      TEIL (datenbank|medien) entschlüsselt ausgeben
#   sicherung schluessel                    neues Schlüsselpaar erzeugen
#
# Unverschlüsselte Daten werden nie auf die Platte geschrieben: pg_dump und tar schreiben
# direkt in age.
#
# Sicherungsaufträge (ADR 0042) stellt man in bintafeln ein (Tabelle core_sicherungsauftrag): Ziel
# (Sicherungsordner oder ein Ordner unter /media bzw. /mnt), Wochentage, Uhrzeit, Aufbewahrung nach
# Anzahl und/oder Tagen. Der Dienst liest sie alle 15 Sekunden, meldet Lebenszeichen, sichtbare
# Ziele und den Stand jedes Auftrags zurück und führt fällige oder angeforderte Aufträge aus.
# Alle 30 Minuten beendet er sich und wird von Docker neu gestartet, damit inzwischen
# eingehängte Medien unter /media und /mnt sichtbar werden.
# ZIEL wird in ausfuehren() bewusst nur in einer Subshell geändert (siehe dort).
# shellcheck disable=SC2031
set -eu
# Die BusyBox-Shell des Images kennt pipefail.
# shellcheck disable=SC3040
set -o pipefail

STANDARD_ZIEL=/sicherungen
ZIEL="$STANDARD_ZIEL"
MEDIEN=/daten/media
PRIVATER_SCHLUESSEL=/schluessel
ANZAHL="${SICHERUNG_ANZAHL:-14}"
TAGE=0
SCHLUESSEL="${SICHERUNG_SCHLUESSEL:-}"
NAMENSMUSTER='^[0-9]{4}-[0-9]{2}-[0-9]{2}_[0-9]{6}$'
# Ein Lauf, der länger als so viele Minuten als „läuft“ gilt, ist abgebrochen worden (z. B. Server
# neu gestartet); der Auftrag ist dann wieder frei.
LAUF_HOECHSTENS=180
# Zeitangaben der Datenbank in der Zeitzone der Tafel
export PGTZ="${TZ:-Europe/Berlin}"

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
    if [ -f "$ZIEL/status.txt" ]; then
        sed -n "s/^$1=//p" "$ZIEL/status.txt" | head -n 1
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
    } > "$ZIEL/status.txt.tmp"
    chmod 644 "$ZIEL/status.txt.tmp"
    mv "$ZIEL/status.txt.tmp" "$ZIEL/status.txt"
}

einstellungen_pruefen() {
    echo "$ANZAHL" | grep -Eq '^[0-9]+$' || fehler "Anzahl muss eine Zahl sein, nicht '$ANZAHL'."
    echo "$TAGE" | grep -Eq '^[0-9]+$' || fehler "Tage müssen eine Zahl sein, nicht '$TAGE'."
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

# Zeitstempel eines Sicherungsnamens als Zahl, z. B. 2026-01-05_123000 -> 20260105123000
als_zahl() {
    echo "$1" | tr -d '_-'
}

# Behält die neueste Sicherung immer; ältere fallen weg, wenn sie über ANZAHL hinausgehen
# (0 = keine Grenze) oder älter als TAGE Tage sind (0 = keine Grenze).
aufraeumen() {
    grenze=0
    if [ "$TAGE" -gt 0 ]; then
        grenze=$(als_zahl "$(date -d "@$(( $(date +%s) - TAGE * 86400 ))" '+%Y-%m-%d_%H%M%S')")
    fi
    nummer=0
    for alt in $(find "$ZIEL" -mindepth 1 -maxdepth 1 -type d | sed 's|.*/||' \
                 | grep -E "$NAMENSMUSTER" | sort -r); do
        nummer=$((nummer + 1))
        [ "$nummer" -eq 1 ] && continue
        if { [ "$ANZAHL" -gt 0 ] && [ "$nummer" -gt "$ANZAHL" ]; } \
            || { [ "$grenze" -gt 0 ] && [ "$(als_zahl "$alt")" -lt "$grenze" ]; }; then
            rm -rf "${ZIEL:?}/$alt"
            log "Alte Sicherung $alt in $ZIEL gelöscht."
        fi
    done
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
        status_schreiben fehler "Die Sicherung ist fehlgeschlagen (Details: docker compose logs backup)."
        fehler "Sicherung $name fehlgeschlagen."
    fi
}

# --- Sicherungsaufträge aus der Datenbank (ADR 0042) -------------------------------------------

# SQL von stdin ausführen; Werte über -v NAME=WERT, im SQL als :'NAME' (sicher gequotet)
sql() {
    psql -X -q -At -v ON_ERROR_STOP=1 "$@"
}

tabelle_da() {
    [ "$(echo "SELECT to_regclass('core_sicherungsauftrag') IS NOT NULL;" | sql 2>/dev/null)" = t ]
}

# Ordner unter /media und /mnt (zwei Ebenen) mit freiem und gesamtem Platz in KB: PFAD|FREI|GESAMT
ziele_finden() {
    for basis in /media /mnt; do
        [ -d "$basis" ] || continue
        find "$basis" -mindepth 1 -maxdepth 2 -type d ! -name bintafeln ! -name '.*' 2>/dev/null \
            | grep -v '|' | sort | while read -r ordner; do
                platz=$(df -Pk "$ordner" 2>/dev/null | awk 'NR == 2 { print $4 "|" $2 }')
                [ -n "$platz" ] && echo "$ordner|$platz"
            done
    done
}

dienst_melden() {
    schluessel_ok=false
    case "$SCHLUESSEL" in age1*) schluessel_ok=true ;; esac
    sql -v ziele="$(ziele_finden)" -v ok="$schluessel_ok" <<'SQL'
INSERT INTO core_sicherungsdienst (id, letzter_kontakt, schluessel_ok, ziele)
VALUES (1, now(), :'ok'::boolean, :'ziele')
ON CONFLICT (id) DO UPDATE
SET letzter_kontakt = now(), schluessel_ok = :'ok'::boolean, ziele = :'ziele';
SQL
}

# Fällige oder angeforderte Aufträge: ID|art (art = angefordert oder plan)
faellige() {
    sql -v hoechstens="$LAUF_HOECHSTENS" <<'SQL'
SELECT id || '|' || CASE WHEN angefordert_am IS NOT NULL THEN 'angefordert' ELSE 'plan' END
FROM core_sicherungsauftrag
WHERE (laeuft_seit IS NULL OR laeuft_seit < now() - make_interval(mins => :'hoechstens'::int))
  AND (angefordert_am IS NOT NULL
       OR (aktiv
           AND position(extract(isodow FROM now())::text IN wochentage) > 0
           AND localtime >= uhrzeit
           AND (geplant_am IS NULL OR geplant_am < current_date)))
ORDER BY standard DESC, id;
SQL
}

# Ordner, in den ein Auftrag sichert: der Sicherungsordner oder ZIEL/bintafeln unter /media, /mnt
zielordner() {
    if [ -z "$1" ]; then
        echo "$STANDARD_ZIEL"
        return
    fi
    case "$1" in
        /media/*|/mnt/*) ;;
        *) return 1 ;;
    esac
    case "$1" in
        */../*|*/..|*'|'*) return 1 ;;
    esac
    [ -d "$1" ] || return 1
    echo "$1/bintafeln"
}

# Stände (NAME|KB, neueste zuerst) und Platz am Ziel zurückmelden
bestand_melden() {
    staende=""
    frei=""
    gesamt=""
    if [ -d "$2" ]; then
        staende=$(find "$2" -mindepth 1 -maxdepth 1 -type d | sed 's|.*/||' \
            | grep -E "$NAMENSMUSTER" | sort -r | while read -r n; do
                echo "$n|$(du -sk "$2/$n" | cut -f1)"
            done)
        frei=$(df -Pk "$2" | awk 'NR == 2 { print $4 * 1024 }')
        gesamt=$(df -Pk "$2" | awk 'NR == 2 { print $2 * 1024 }')
    fi
    sql -v id="$1" -v staende="$staende" -v frei="$frei" -v gesamt="$gesamt" <<'SQL'
UPDATE core_sicherungsauftrag
SET staende = :'staende', frei_bytes = NULLIF(:'frei', '')::bigint,
    gesamt_bytes = NULLIF(:'gesamt', '')::bigint
WHERE id = :'id'::int;
SQL
}

ergebnis_melden() {
    sql -v id="$1" -v ergebnis="$2" -v meldung="$3" <<'SQL'
UPDATE core_sicherungsauftrag
SET laeuft_seit = NULL, letzter_versuch = now(), ergebnis = :'ergebnis', meldung = :'meldung',
    letzte_erfolgreiche = CASE WHEN :'ergebnis' = 'ok' THEN now() ELSE letzte_erfolgreiche END
WHERE id = :'id'::int;
SQL
}

# ausfuehren ID ART: einen Auftrag ausführen und das Ergebnis zurückmelden; 1 bei Fehler
ausfuehren() {
    zeile=$(sql -v id="$1" -v art="$2" <<'SQL'
UPDATE core_sicherungsauftrag
SET laeuft_seit = now(), angefordert_am = NULL, angefordert_von = '',
    geplant_am = CASE WHEN :'art' = 'plan' THEN current_date ELSE geplant_am END
WHERE id = :'id'::int
RETURNING coalesce(anzahl, 0) || '|' || coalesce(tage, 0) || '|' || ziel;
SQL
)
    anzahl=${zeile%%|*}
    rest=${zeile#*|}
    tage=${rest%%|*}
    ziel=${rest#*|}
    if ! ordner=$(zielordner "$ziel"); then
        log "Auftrag $1: Ziel $ziel ist nicht erreichbar."
        ergebnis_melden "$1" fehler "Das Ziel $ziel ist nicht erreichbar (Medium nicht angeschlossen oder nicht eingehängt?)."
        return 1
    fi
    # Absichtlich in einer Subshell: Ziel und Aufbewahrung gelten nur für diesen Lauf, und ein
    # Fehler (exit in fehler()) beendet nicht den ganzen Dienst.
    # shellcheck disable=SC2030
    if (ZIEL="$ordner"; ANZAHL="$anzahl"; TAGE="$tage"; sichern); then
        ergebnis=ok
    else
        ergebnis=fehler
    fi
    meldung=$(ZIEL="$ordner" status_wert meldung)
    ergebnis_melden "$1" "$ergebnis" "${meldung:-Sicherung fehlgeschlagen.}"
    bestand_melden "$1" "$ordner"
    [ "$ergebnis" = ok ]
}

alle_bestaende_melden() {
    for zeile in $(echo "SELECT id || '|' || replace(ziel, ' ', '%20') FROM core_sicherungsauftrag;" | sql); do
        ziel=$(echo "${zeile#*|}" | sed 's/%20/ /g')
        ordner=$(zielordner "$ziel") || ordner=""
        bestand_melden "${zeile%%|*}" "$ordner"
    done
}

zeitplan() {
    log "Dienst läuft: Sicherungsaufträge werden aus bintafeln gelesen (Einstellungen → Sicherungen)."
    if [ -z "$SCHLUESSEL" ]; then
        log "Hinweis: Noch kein Sicherungsschlüssel eingetragen. Einrichten mit: ./betrieb schluessel"
        status_schreiben nicht_eingerichtet "Kein Sicherungsschlüssel in .env eingetragen."
    fi
    runde=0
    while true; do
        if tabelle_da; then
            dienst_melden || log "Lebenszeichen konnte nicht gemeldet werden."
            for zeile in $(faellige || true); do
                ausfuehren "${zeile%%|*}" "${zeile#*|}" || true
            done
            # Alle 10 Minuten Stände und Platz aller Ziele melden (z. B. neu angesteckte Platten)
            if [ $((runde % 40)) -eq 0 ]; then
                alle_bestaende_melden || true
            fi
            runde=$((runde + 1))
        fi
        # Alle 30 Minuten beenden; Docker startet den Dienst sofort neu (restart: unless-stopped).
        # Erst beim Start bindet Docker /media und /mnt mit allen gerade eingehängten Medien ein.
        if [ "$runde" -ge 120 ]; then
            log "Neustart des Dienstes, damit neu eingehängte Medien sichtbar werden."
            exit 0
        fi
        sleep 15
    done
}

jetzt() {
    einstellungen_pruefen
    id=""
    if tabelle_da; then
        id=$(echo "SELECT id FROM core_sicherungsauftrag WHERE standard ORDER BY id LIMIT 1;" | sql)
    fi
    if [ -n "$id" ]; then
        ausfuehren "$id" manuell || fehler "Sicherung fehlgeschlagen."
    else
        sichern
    fi
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
    jetzt) jetzt ;;
    pruefen) pruefen "${2:-}" ;;
    entschluesseln) entschluesseln "${2:-}" "${3:-}" ;;
    schluessel) age-keygen ;;
    *) fehler "Unbekannter Befehl '$1'." ;;
esac

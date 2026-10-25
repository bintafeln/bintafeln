#!/usr/bin/env bash
# Ende-zu-Ende-Test für Sicherung und Wiederherstellung mit dem echten Docker-Compose-Aufbau.
# Läuft in GitHub Actions; lokal nur in einer Wegwerf-Umgebung ausführen, er überschreibt .env
# und löscht am Ende alle Container und Volumes dieses Projekts.
set -euo pipefail
cd "$(dirname "$(readlink -f "$0")")/.."

export COMPOSE_PROJECT_NAME=bintafeln-e2e
SCHLUESSELDATEI=$(mktemp)

EXTERN=/mnt/bintafeln-e2e-ziel
mnt_rm() { docker run --rm -v /mnt:/mnt alpine:3 rm -rf "$1" > /dev/null 2>&1 || true; }

aufraeumen() {
    docker compose down -v --remove-orphans > /dev/null 2>&1 || true
    rm -f "$SCHLUESSELDATEI"
    mnt_rm "$EXTERN"
}
trap aufraeumen EXIT

pruefe() { echo "PRÜFE: $1"; }
python_in_app() { docker compose exec -T app python manage.py shell -c "$1" 2> /dev/null | tail -n 1; }
# warte SEKUNDEN PYTHON: bis der Python-Ausdruck in der App "ja" ausgibt
warte() {
    local _
    for _ in $(seq 1 "$1"); do
        [[ "$(python_in_app "$2")" == ja ]] && return 0
        sleep 1
    done
    echo "Zeitüberschreitung beim Warten auf: $2"
    return 1
}
AUFTRAG="from apps.core.models import SicherungsAuftrag as A"

cp .env.example .env
sed -i "s|^DJANGO_SECRET_KEY=.*|DJANGO_SECRET_KEY=nur-fuer-den-test-$RANDOM$RANDOM|" .env
sed -i "s|^POSTGRES_PASSWORD=.*|POSTGRES_PASSWORD=nur-fuer-den-test|" .env
sed -i "s|^HTTP_PORT=.*|HTTP_PORT=${E2E_HTTP_PORT:-8080}|; s|^HTTPS_PORT=.*|HTTPS_PORT=${E2E_HTTPS_PORT:-8443}|" .env
sed -i "s|^BINTAFELN_SICHERUNG_PFAD=.*|BINTAFELN_SICHERUNG_PFAD=./sicherungen-e2e|" .env
sudo_rm() { docker run --rm -v "$PWD:/w" alpine:3 rm -rf "/w/$1" 2> /dev/null || rm -rf "$1"; }
sudo_rm sicherungen-e2e

${E2E_BAUEN:-true} && docker compose build
docker compose up -d --wait

pruefe "Ohne Schlüssel meldet der Dienst 'nicht eingerichtet'"
for _ in $(seq 1 20); do [[ -f sicherungen-e2e/status.txt ]] && break; sleep 1; done
grep -q '^ergebnis=nicht_eingerichtet' sicherungen-e2e/status.txt
if ./betrieb sichern > /dev/null 2>&1; then echo "Sichern ohne Schlüssel hätte scheitern müssen"; exit 1; fi

pruefe "Schlüssel erzeugen"
ausgabe=$(./betrieb schluessel)
grep '^AGE-SECRET-KEY-' <<< "$ausgabe" > "$SCHLUESSELDATEI"
grep -q '^BINTAFELN_SICHERUNG_SCHLUESSEL=age1' .env
docker compose up -d --wait

pruefe "Testdaten anlegen und sichern"
python_in_app "from apps.core.models import TafelEinstellungen as T; t=T.laden(); t.name='Vorher-Tafel'; t.save()"
docker compose exec -T app sh -c 'mkdir -p /app/data/media/oeffentlich && echo probe > /app/data/media/oeffentlich/probe.txt'
./betrieb sichern
name=$(find sicherungen-e2e -mindepth 1 -maxdepth 1 -type d -printf '%f\n' | sort | tail -n 1)
echo "Sicherung: $name"
grep -q '^ergebnis=ok' sicherungen-e2e/status.txt

pruefe "Sicherung ist verschlüsselt"
head -c 21 "sicherungen-e2e/$name/datenbank.dump.age" | grep -q 'age-encryption.org/v1'
head -c 21 "sicherungen-e2e/$name/medien.tar.age" | grep -q 'age-encryption.org/v1'
if grep -q 'Vorher-Tafel' "sicherungen-e2e/$name/datenbank.dump.age"; then echo "Klartext in der Sicherung"; exit 1; fi

pruefe "Daten verändern"
python_in_app "from apps.core.models import TafelEinstellungen as T; t=T.laden(); t.name='Nachher-Tafel'; t.save()"
docker compose exec -T app sh -c 'rm /app/data/media/oeffentlich/probe.txt && echo neu > /app/data/media/neu.txt'

pruefe "Falscher Schlüssel wird abgelehnt, ohne etwas zu verändern"
falsch=$(mktemp)
docker compose run --rm --no-deps -T backup schluessel 2> /dev/null | grep '^AGE-SECRET-KEY-' > "$falsch"
if ./betrieb wiederherstellen "$name" --schluessel "$falsch" --ja > /dev/null 2>&1; then
    echo "Wiederherstellen mit falschem Schlüssel hätte scheitern müssen"; exit 1
fi
rm -f "$falsch"
[[ "$(python_in_app "from apps.core.models import TafelEinstellungen as T; print(T.laden().name)")" == "Nachher-Tafel" ]]

pruefe "Wiederherstellen"
./betrieb wiederherstellen "$name" --schluessel "$SCHLUESSELDATEI" --ja
[[ "$(python_in_app "from apps.core.models import TafelEinstellungen as T; print(T.laden().name)")" == "Vorher-Tafel" ]]
docker compose exec -T app test -f /app/data/media/oeffentlich/probe.txt
if docker compose exec -T app test -e /app/data/media/neu.txt; then echo "neu.txt hätte weg sein müssen"; exit 1; fi

pruefe "Vor dem Wiederherstellen wurde der damalige Stand gesichert"
[[ $(find sicherungen-e2e -mindepth 1 -maxdepth 1 -type d | wc -l) -eq 2 ]]

pruefe "Anwendung läuft wieder"
curl -fsS "http://localhost:${E2E_HTTP_PORT:-8080}/healthz/" | grep -q ok

pruefe "Aufbewahrung: nur so viele Stände wie im Standard-Auftrag eingestellt"
python_in_app "$AUFTRAG; A.objects.filter(standard=True).update(anzahl=2)"
sleep 1
./betrieb sichern > /dev/null
[[ $(find sicherungen-e2e -mindepth 1 -maxdepth 1 -type d | wc -l) -eq 2 ]]
[[ ! -d "sicherungen-e2e/$name" ]]

pruefe "Der Dienst meldet sich und führt eine Sofort-Sicherung aus (Einstellungen → Sicherungen)"
DIENST="from apps.core.models import SicherungsDienst as D; from django.utils import timezone as tz"
warte 60 "$DIENST; d=D.objects.first(); print('ja' if d and d.schluessel_ok and tz.now()-d.letzter_kontakt<tz.timedelta(minutes=1) else 'nein')"
python_in_app "$AUFTRAG; from django.utils import timezone as tz; A.objects.filter(standard=True).update(angefordert_am=tz.now(), ergebnis='')"
warte 90 "$AUFTRAG; a=A.objects.get(standard=True); print('ja' if a.ergebnis=='ok' and not a.angefordert_am and a.staende else 'nein')"

pruefe "Externes Ziel unter /mnt: erscheint zur Auswahl, Zeitplan sichert dorthin"
docker run --rm -v /mnt:/mnt alpine:3 mkdir -p "$EXTERN"
warte 60 "$DIENST; print('ja' if '$EXTERN|' in D.objects.first().ziele else 'nein')"
python_in_app "$AUFTRAG; import datetime as dt; A.objects.create(name='Extern', ziel='$EXTERN', uhrzeit=dt.time(0, 0), tage=7)"
warte 90 "$AUFTRAG; a=A.objects.get(name='Extern'); print('ja' if a.ergebnis=='ok' and a.geplant_am else 'nein')"
docker run --rm -v /mnt:/mnt alpine:3 sh -c "ls $EXTERN/bintafeln/*/datenbank.dump.age" > /dev/null

pruefe "Nicht erreichbares Ziel ergibt eine verständliche Meldung"
python_in_app "$AUFTRAG; from django.utils import timezone as tz; import datetime as dt; A.objects.create(name='Weg', ziel='/mnt/gibt-es-nicht', uhrzeit=dt.time(23, 59), wochentage='', anzahl=1, angefordert_am=tz.now())"
warte 60 "$AUFTRAG; a=A.objects.get(name='Weg'); print('ja' if a.ergebnis=='fehler' and 'nicht erreichbar' in a.meldung else 'nein')"

sudo_rm sicherungen-e2e
echo "Alle Prüfungen bestanden."

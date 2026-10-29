#!/bin/sh
# Startet bintafeln: wartet auf die Datenbank, führt Migrationen aus und
# sammelt die statischen Dateien ein. Danach startet der eigentliche Befehl.
set -eu

versuche=30
until python -c "import django; django.setup(); from django.db import connection; connection.ensure_connection()" >/dev/null 2>&1; do
    versuche=$((versuche - 1))
    if [ "$versuche" -le 0 ]; then
        echo "Datenbank nicht erreichbar – Abbruch." >&2
        exit 1
    fi
    echo "Warte auf die Datenbank …"
    sleep 2
done

python manage.py migrate --noinput
python manage.py collectstatic --noinput --verbosity 0

# Beim Webserver: gesammelte Benachrichtigungen alle fünf Minuten verschicken (ADR 0086) und,
# wenn eingeschaltet und fällig, die Meldung im bintafeln-Verzeichnis (ADR 0089).
# Einmalige Befehle (z. B. docker compose run app python manage.py …) starten das nicht.
if [ "${1:-}" = "gunicorn" ]; then
    (
        while sleep 300; do
            python manage.py benachrichtigungen_senden || true
            python manage.py verzeichnis_melden || true
        done
    ) &
fi

exec "$@"

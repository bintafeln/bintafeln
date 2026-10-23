# Dienst "backup": gleiche PostgreSQL-Version wie der Dienst db, dazu age zum Verschlüsseln.
FROM postgres:17-alpine

RUN apk add --no-cache age tzdata

COPY sicherung.sh /usr/local/bin/sicherung
RUN chmod 755 /usr/local/bin/sicherung

ENTRYPOINT ["sicherung"]
CMD ["zeitplan"]

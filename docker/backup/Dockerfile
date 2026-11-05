# Dienst "backup": gleiche PostgreSQL-Version wie der Dienst db, dazu age zum Verschlüsseln und
# rclone für Sicherungen außer Haus (SFTP, FTP, S3, WebDAV/Nextcloud …; ADR 0106).
FROM postgres:17-alpine

RUN apk add --no-cache age rclone tzdata

COPY sicherung.sh /usr/local/bin/sicherung
RUN chmod 755 /usr/local/bin/sicherung

ENTRYPOINT ["sicherung"]
CMD ["zeitplan"]

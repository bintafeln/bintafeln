# Dienst "updater" (ADR 0043): führt Updates aus, die in bintafeln angefordert werden.
# Docker-CLI mit Compose und git; bash für ./betrieb.
FROM docker:28-cli

RUN apk add --no-cache bash

COPY updater.sh /usr/local/bin/updater
RUN chmod 755 /usr/local/bin/updater

ENTRYPOINT ["updater"]
CMD ["dienst"]

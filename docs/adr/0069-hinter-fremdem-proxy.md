# 0069: Betrieb hinter einem fremden Reverse Proxy

- Status: Angenommen
- Datum: 2026-10-26

## Problem

Manche Tafeln leiten die Ports 80 und 443 schon auf ein anderes Gerät, z. B. eine Synology, deren
Reverse Proxy weitere Dienste ausliefert. Der Router kann dieselben Ports nicht zusätzlich an die
bintafeln-VM geben. Leitet der fremde Proxy `https://domain` an `http://VM:80` weiter, holt Caddy
mit gesetzter Domain trotzdem ein eigenes Zertifikat und leitet http auf https um – die Anfragen
des Proxys landen in einer Schleife.

## Entscheidung

`docker/hinter-fremdem-proxy.yml` (über `COMPOSE_FILE` in `.env` eingeschaltet) lässt Caddy nur
auf Port 80 antworten (`SITE_ADDRESS ":80"`) und übernimmt `X-Forwarded-Proto` und
`X-Forwarded-For` nur von Adressen im lokalen Netz (`private_ranges`). `BINTAFELN_DOMAIN` bleibt
gesetzt, bintafeln läuft also im Produktionsmodus (sichere Cookies, HSTS, nur diese Domain).
Wie beim gemeinsamen Proxy (ADR 0022), nur ohne gemeinsames Docker-Netz, weil der Proxy auf
einem anderen Gerät läuft.

## Begründung

Eine Zeile in `.env` statt eines Umbaus des Netzes der Tafel. TLS bleibt Pflicht, nur macht es
der fremde Proxy; Kopfzeilen nimmt bintafeln nur aus dem lokalen Netz an, damit niemand von außen
https oder eine fremde Adresse vortäuschen kann.

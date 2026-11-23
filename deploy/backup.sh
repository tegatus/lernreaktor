#!/usr/bin/env bash
# LernReaktor – Sicherung von Datenbank und hochgeladenen Dateien (läuft täglich per systemd-Timer).
# Wiederherstellen: siehe deploy/INSTALLATION.md, Abschnitt «Sicherung zurückspielen».
set -euo pipefail
ZIEL=/var/backups/lernreaktor
BEHALTEN_TAGE=14
STEMPEL=$(date +%Y-%m-%d_%H%M)
umask 077
mkdir -p "$ZIEL"
runuser -u postgres -- pg_dump -Fc lernreaktor > "$ZIEL/datenbank_$STEMPEL.dump"
tar -czf "$ZIEL/dateien_$STEMPEL.tar.gz" -C /var/lib/lernreaktor dateien
find "$ZIEL" -maxdepth 1 -type f \( -name 'datenbank_*.dump' -o -name 'dateien_*.tar.gz' \) -mtime +"$BEHALTEN_TAGE" -delete
echo "Sicherung erstellt: $ZIEL/*_$STEMPEL.*"

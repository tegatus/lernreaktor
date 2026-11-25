#!/usr/bin/env bash
# LernReaktor – Installation auf Ubuntu (getestet für 24.04/26.04) mit PostgreSQL, Gunicorn und nginx.
#
# Aufruf (als Benutzer mit sudo-Rechten), aus dem geklonten Repository:
#   sudo git clone https://github.com/tegatus/lernreaktor.git /opt/lernreaktor
#   sudo /opt/lernreaktor/deploy/install.sh [--ip 203.0.113.10] [--firewall]
#
# Das Skript kann gefahrlos mehrfach ausgeführt werden; bestehende Daten und Schlüssel bleiben erhalten.
set -euo pipefail

APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
DATEN=/var/lib/lernreaktor
KONFIG=/etc/lernreaktor
ENV_DATEI=$KONFIG/lernreaktor.env
DIENSTKONTO=lernreaktor
DB_NAME=lernreaktor
SERVER_IP=""
FIREWALL=0

while [[ $# -gt 0 ]]; do
  case "$1" in
    --ip) SERVER_IP="$2"; shift 2 ;;
    --firewall) FIREWALL=1; shift ;;
    -h|--help) sed -n '2,9p' "$0"; exit 0 ;;
    *) echo "Unbekannte Option: $1" >&2; exit 1 ;;
  esac
done

schritt() { printf '\n\033[1;33m==> %s\033[0m\n' "$*"; }
[[ $EUID -eq 0 ]] || { echo "Bitte mit sudo ausführen." >&2; exit 1; }

# systemctl nur verwenden, wenn systemd läuft (in Containern zum Testen nicht der Fall)
dienst() {
  if [[ -d /run/systemd/system ]]; then systemctl "$@"; else echo "   (systemd nicht aktiv – übersprungen: systemctl $*)"; fi
}

schritt "Systempakete installieren"
export DEBIAN_FRONTEND=noninteractive
apt-get update -q
apt-get install -y -q python3 python3-venv python3-pip postgresql nginx openssl libpq5 \
  certbot python3-certbot-nginx fonts-liberation

schritt "Dienstkonto und Ordner"
if ! id "$DIENSTKONTO" &>/dev/null; then
  useradd --system --home-dir "$DATEN" --shell /usr/sbin/nologin "$DIENSTKONTO"
fi
install -d -o "$DIENSTKONTO" -g "$DIENSTKONTO" -m 750 "$DATEN" "$DATEN/dateien" "$DATEN/instance"
install -d -o root -g "$DIENSTKONTO" -m 750 "$KONFIG"
install -d -o root -g root -m 700 /var/backups/lernreaktor

schritt "PostgreSQL: Datenbank und Rolle (Anmeldung über lokalen Socket, kein Passwort nötig)"
dienst enable --now postgresql
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_roles WHERE rolname='$DIENSTKONTO'" | grep -q 1; then
  runuser -u postgres -- psql -qc "CREATE ROLE $DIENSTKONTO LOGIN"
fi
if ! runuser -u postgres -- psql -tAc "SELECT 1 FROM pg_database WHERE datname='$DB_NAME'" | grep -q 1; then
  runuser -u postgres -- createdb -O "$DIENSTKONTO" -E UTF8 "$DB_NAME"
fi

schritt "Konfiguration $ENV_DATEI"
if [[ ! -f $ENV_DATEI ]]; then
  umask 027
  cat > "$ENV_DATEI" <<EOF
# LernReaktor – Konfiguration (nur root und Dienstkonto lesbar). Nach Änderungen: sudo systemctl restart lernreaktor
SECRET_KEY=$(openssl rand -hex 32)
DATABASE_URL=postgresql+psycopg:///$DB_NAME?host=/var/run/postgresql
UPLOAD_DIR=$DATEN/dateien
LERNREAKTOR_INSTANCE=$DATEN/instance
LERNREAKTOR_HTTPS=1
LERNREAKTOR_PROXY=1
INAKTIV_MINUTEN=60
# Öffentliche Adresse für QR-Codes auf Übungsblättern (ohne: Adresse der jeweiligen Anfrage)
#BASIS_URL=https://lernreaktor.example.ch
# KI-Assistent (optional): Schlüssel aus der Claude Console eintragen und Dienst neu starten
#ANTHROPIC_API_KEY=
EOF
  chown root:"$DIENSTKONTO" "$ENV_DATEI"
  chmod 640 "$ENV_DATEI"
  umask 022
else
  echo "   vorhanden – unverändert gelassen"
fi

schritt "Python-Umgebung und Abhängigkeiten"
[[ -d $APP_DIR/.venv ]] || python3 -m venv "$APP_DIR/.venv"
"$APP_DIR/.venv/bin/pip" install -q --upgrade pip
"$APP_DIR/.venv/bin/pip" install -q -r "$APP_DIR/deploy/requirements-server.txt"

schritt "Verwaltungsbefehle"
install -m 755 "$APP_DIR/deploy/lernreaktor-flask" /usr/local/bin/lernreaktor-flask
sed -i "s#__APP_DIR__#$APP_DIR#g" /usr/local/bin/lernreaktor-flask
install -m 700 "$APP_DIR/deploy/backup.sh" /usr/local/sbin/lernreaktor-backup

schritt "Datenbank einrichten (Tabellen, BiVo-Kompetenzen, Lernziele, Beispielaufgaben)"
lernreaktor-flask init-db

schritt "systemd-Dienste"
sed "s#__APP_DIR__#$APP_DIR#g" "$APP_DIR/deploy/lernreaktor.service" > /etc/systemd/system/lernreaktor.service
cp "$APP_DIR/deploy/lernreaktor-backup.service" "$APP_DIR/deploy/lernreaktor-backup.timer" /etc/systemd/system/
dienst daemon-reload
dienst enable --now lernreaktor.service lernreaktor-backup.timer
dienst restart lernreaktor.service

schritt "nginx und HTTPS"
SITE=/etc/nginx/sites-available/lernreaktor
if [[ -f $SITE ]] && grep -q letsencrypt "$SITE"; then
  echo "   Let's-Encrypt-Konfiguration vorhanden – unverändert gelassen"
else
  [[ -n $SERVER_IP ]] || SERVER_IP="$(hostname -I | awk '{print $1}')"
  ZERT=/etc/ssl/lernreaktor
  install -d -m 755 "$ZERT"
  if [[ ! -f $ZERT/lernreaktor.crt ]]; then
    echo "   selbstsigniertes Zertifikat für $SERVER_IP (bis eine Domain eingerichtet ist)"
    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:prime256v1 -nodes -days 825 \
      -keyout "$ZERT/lernreaktor.key" -out "$ZERT/lernreaktor.crt" \
      -subj "/CN=$SERVER_IP/O=LernReaktor" -addext "subjectAltName=IP:$SERVER_IP" 2>/dev/null
    chmod 600 "$ZERT/lernreaktor.key"
  fi
  sed -e "s#__SERVER_NAME__#$SERVER_IP#g" -e "s#__APP_DIR__#$APP_DIR#g" \
      -e "s#__CERT__#$ZERT/lernreaktor.crt#" -e "s#__KEY__#$ZERT/lernreaktor.key#" \
      "$APP_DIR/deploy/nginx-lernreaktor.conf" > "$SITE"
  # ohne IPv6 im Kernel (z. B. deaktiviert) kann nginx nicht auf [::] lauschen
  [[ -f /proc/net/if_inet6 ]] || sed -i '/listen \[::\]/d' "$SITE"
fi
ln -sf "$SITE" /etc/nginx/sites-enabled/lernreaktor
rm -f /etc/nginx/sites-enabled/default
nginx -t
dienst enable nginx
dienst reload nginx || dienst restart nginx

if [[ $FIREWALL -eq 1 ]]; then
  schritt "Firewall (ufw): nur SSH, HTTP und HTTPS"
  apt-get install -y -q ufw
  ufw allow OpenSSH
  ufw allow 'Nginx Full'
  ufw --force enable
fi

schritt "Fertig"
cat <<EOF
LernReaktor läuft unter:  https://${SERVER_IP:-<Server-IP>}
  (selbstsigniertes Zertifikat: der Browser warnt einmal – bis eine Domain eingerichtet ist)

Nächste Schritte:
  1. Lehrpersonen-Konto anlegen (Passwort wird verdeckt abgefragt):
       sudo lernreaktor-flask create-lp vorname.name "Vorname Name"
  2. Später mit Domain:  sudo $APP_DIR/deploy/domain.sh lernreaktor.example.ch admin@example.ch
  3. Aktualisieren:      sudo $APP_DIR/deploy/update.sh

Status/Protokoll:  systemctl status lernreaktor   ·   journalctl -u lernreaktor -f
Sicherungen:       /var/backups/lernreaktor (täglich 02:30, 14 Tage) – bitte zusätzlich extern kopieren!
EOF

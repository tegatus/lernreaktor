#!/usr/bin/env bash
# Domain einrichten und ein Let's-Encrypt-Zertifikat holen (ersetzt das selbstsignierte Zertifikat).
# Voraussetzung: der DNS-Eintrag (A/AAAA) der Domain zeigt bereits auf diesen Server, Ports 80/443 sind offen.
#   sudo /opt/lernreaktor/deploy/domain.sh lernreaktor.example.ch admin@example.ch
set -euo pipefail
[[ $EUID -eq 0 ]] || { echo "Bitte mit sudo ausführen." >&2; exit 1; }
DOMAIN="${1:?Domain angeben, z. B. lernreaktor.example.ch}"
MAIL="${2:?E-Mail-Adresse für Zertifikats-Warnungen angeben}"
[[ $DOMAIN =~ ^[A-Za-z0-9.-]+\.[A-Za-z]{2,}$ ]] || { echo "Ungültige Domain: $DOMAIN" >&2; exit 1; }
APP_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
SITE=/etc/nginx/sites-available/lernreaktor

echo "==> nginx auf $DOMAIN umstellen"
sed -e "s#__SERVER_NAME__#$DOMAIN#g" -e "s#__APP_DIR__#$APP_DIR#g" \
    -e "s#__CERT__#/etc/ssl/lernreaktor/lernreaktor.crt#" -e "s#__KEY__#/etc/ssl/lernreaktor/lernreaktor.key#" \
    "$APP_DIR/deploy/nginx-lernreaktor.conf" > "$SITE"
# ohne IPv6 im Kernel (z. B. deaktiviert) kann nginx nicht auf [::] lauschen
[[ -f /proc/net/if_inet6 ]] || sed -i '/listen \[::\]/d' "$SITE"
nginx -t && systemctl reload nginx

echo "==> Zertifikat von Let's Encrypt holen"
certbot --nginx -d "$DOMAIN" -m "$MAIL" --agree-tos --no-eff-email --redirect --non-interactive
# Markierung für install.sh/update: Let's-Encrypt-Konfiguration nicht überschreiben
grep -q letsencrypt "$SITE" && echo "==> Fertig: https://$DOMAIN (Zertifikat erneuert sich automatisch)"

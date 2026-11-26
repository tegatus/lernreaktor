# LernReaktor auf einem Ubuntu-Server installieren

Für Ubuntu 26.04 LTS (auch 24.04) mit PostgreSQL, Gunicorn und nginx. Dauer: ca. 10 Minuten.

**Auf einem Server mit bereits laufendem Reverse-Proxy** (z. B. Caddy in Docker, der andere Seiten über ein
Docker-Netzwerk anspricht statt über Host-Ports): Dieses Skript braucht die Ports 80/443 selbst und passt nicht.
Siehe stattdessen `deploy/docker/` (Container-Variante mit eigenem Postgres, die sich ins bestehende
Docker-Netzwerk einhängt).

## Was eingerichtet wird

| Teil | Wo | Bemerkung |
|---|---|---|
| Programmcode | `/opt/lernreaktor` | gehört root, für die App nur lesbar |
| Daten (Uploads, PDFs) | `/var/lib/lernreaktor` | gehört dem Dienstkonto `lernreaktor` |
| Konfiguration | `/etc/lernreaktor/lernreaktor.env` | Secret Key, Datenbank, optional KI-Schlüssel; nur root/lernreaktor lesbar |
| Datenbank | PostgreSQL, Datenbank `lernreaktor` | Anmeldung über lokalen Socket – **es gibt kein Datenbank-Passwort** |
| App-Server | systemd-Dienst `lernreaktor` (Gunicorn auf 127.0.0.1:8000) | gehärtet: darf nur in `/var/lib/lernreaktor` schreiben |
| Webserver | nginx, HTTPS | ohne Domain mit selbstsigniertem Zertifikat, später Let's Encrypt |
| Sicherung | täglich 02:30 nach `/var/backups/lernreaktor` | Datenbank + Dateien, 14 Tage aufbewahrt |

## Installation

Alle Befehle als Benutzer mit sudo-Rechten auf dem Server.

**1. Code holen**

```bash
sudo git clone https://github.com/tegatus/lernreaktor.git /opt/lernreaktor
```

**2. Installationsskript ausführen**

```bash
sudo /opt/lernreaktor/deploy/install.sh
```

Optionen:
- `--ip 203.0.113.10` – öffentliche IP-Adresse für das Zertifikat angeben (sonst wird die erste Adresse des Servers verwendet)
- `--firewall` – aktiviert die Firewall `ufw` und lässt nur SSH, HTTP und HTTPS zu. Nur verwenden, wenn SSH über den
  Standardport 22 läuft und beim Hoster keine eigene Firewall vorgesehen ist.

Das Skript kann gefahrlos erneut ausgeführt werden; Daten, Schlüssel und Zertifikate bleiben erhalten.

**3. Erstes Lehrpersonen-Konto anlegen** (das Passwort wird verdeckt abgefragt)

```bash
sudo lernreaktor-flask create-lp vorname.name "Vorname Name"
sudo lernreaktor-flask set-admin vorname.name   # Admin-Recht: BiVo-Kompetenzliste neu einlesen
```

Admin-Recht wieder entziehen: `sudo lernreaktor-flask set-admin vorname.name --entziehen`.
In der Docker-Variante: `docker exec lernreaktor flask --app run set-admin vorname.name`.

**4. Im Browser öffnen:** `https://<IP-Adresse des Servers>`

Ohne Domain verwendet der Server ein selbstsigniertes Zertifikat. Der Browser zeigt deshalb einmal eine Warnung
(«Verbindung nicht privat») – die Verbindung ist trotzdem verschlüsselt. Über «Erweitert → Weiter» gelangt man zur App.
**Empfehlung:** echte Daten von Lernenden erst erfassen, wenn die Domain mit gültigem Zertifikat eingerichtet ist.

## Domain einrichten (später)

1. Beim Domain-Anbieter einen DNS-Eintrag (Typ A, bei IPv6 zusätzlich AAAA) auf die IP-Adresse des Servers setzen.
2. Warten, bis der Eintrag aktiv ist (`ping lernreaktor.example.ch` zeigt die Server-IP).
3. Zertifikat holen – erneuert sich danach automatisch:

```bash
sudo /opt/lernreaktor/deploy/domain.sh lernreaktor.example.ch it@schule.ch
```

## Aktualisieren

Erstellt zuerst eine Sicherung, holt den neuesten Stand von GitHub, aktualisiert die Pakete und startet neu.
Neue Tabellen und Spalten werden beim Start automatisch ergänzt.

```bash
sudo /opt/lernreaktor/deploy/update.sh
```

## KI-Assistent einschalten (optional)

In `/etc/lernreaktor/lernreaktor.env` die Zeile `#ANTHROPIC_API_KEY=` durch `ANTHROPIC_API_KEY=<Schlüssel>` ersetzen
(Schlüssel aus der Claude Console, dort auch ein Ausgabenlimit setzen), dann:

```bash
sudo systemctl restart lernreaktor
```

## Review-Hinweise mit Claude Code bearbeiten (optional)

Reviewer melden Probleme in Aufgaben und Theorie. Claude Code holt die offenen Hinweise über die
Agent-Schnittstelle und schreibt Vorschläge oder Rückfragen zurück; übernommen wird nur, was die Lehrperson
bestätigt. Claude Code läuft dabei mit dem Claude-Abo, nicht über einen API-Schlüssel.

1. Token erzeugen (`openssl rand -hex 32`) und in `/etc/lernreaktor/lernreaktor.env` als `AGENT_TOKEN=<Token>`
   eintragen (Docker: in `.env`), dann `sudo systemctl restart lernreaktor`. Ohne Token ist die Schnittstelle aus.
2. Die App muss von aussen über HTTPS erreichbar sein (Domain, siehe oben).
3. In Claude Code im Projekt eine geplante Routine anlegen (`/schedule`): Repository `tegatus/lernreaktor`,
   Auftrag `/reviews`, Umgebungsvariablen `LERNREAKTOR_URL=https://<domain>` und
   `LERNREAKTOR_AGENT_TOKEN=<Token>`; die Domain in den Netzwerkeinstellungen der Umgebung erlauben.
   Von Hand geht es jederzeit lokal: beide Variablen setzen und in Claude Code `/reviews` eingeben.

Token wechseln: neuen Wert in der Konfiguration und in der Routine eintragen, Dienst neu starten.

## Sicherungen

- Täglich um 02:30 (verpasste Läufe werden nachgeholt): `/var/backups/lernreaktor/datenbank_<Datum>.dump` und
  `dateien_<Datum>.tar.gz`. Manuell: `sudo lernreaktor-backup`
- **Wichtig:** Sicherungen auf dem gleichen Server schützen nicht vor einem Serverausfall. Den Ordner regelmässig
  an einen anderen Ort kopieren (z. B. Schul-NAS, verschlüsselt).

### Sicherung zurückspielen

```bash
sudo systemctl stop lernreaktor
```
```bash
sudo -u postgres dropdb lernreaktor && sudo -u postgres createdb -O lernreaktor lernreaktor
```
```bash
sudo cat /var/backups/lernreaktor/datenbank_DATUM.dump | sudo -u postgres pg_restore -d lernreaktor --no-owner --role=lernreaktor
```
```bash
sudo tar -xzf /var/backups/lernreaktor/dateien_DATUM.tar.gz -C /var/lib/lernreaktor && sudo chown -R lernreaktor:lernreaktor /var/lib/lernreaktor/dateien
```
```bash
sudo systemctl start lernreaktor
```

(Die Sicherungsdateien sind nur für root lesbar; deshalb liest `sudo cat` die Datei und übergibt sie an `pg_restore`.)

## Fehlersuche

| Frage | Befehl |
|---|---|
| Läuft die App? | `systemctl status lernreaktor` |
| Fehlermeldungen der App | `journalctl -u lernreaktor -n 100` |
| nginx-Konfiguration prüfen | `sudo nginx -t` |
| Wann läuft die nächste Sicherung? | `systemctl list-timers lernreaktor-backup.timer` |
| Passwort einer Lehrperson vergessen | `sudo lernreaktor-flask create-lp neuer.name "Name"` (neues Konto) – Lernende setzt die Lehrperson in der App zurück |

## Arbeiten mit Claude Code auf dem Server

Wird die Installation mit Claude Code auf dem Server durchgeführt, läuft Claude Code als eigener Benutzer
(z. B. `simon_claude`) und **ohne** dauerhafte sudo-Rechte. Die Schritte 1–3 oben benötigen sudo: entweder führt sie
eine Administratorin selbst aus, oder der Benutzer erhält vorübergehend sudo-Rechte, die danach wieder entzogen werden:

```bash
sudo deluser simon_claude sudo
```

Passwörter werden nie im Chat weitergegeben; sudo fragt sie im eigenen Terminal ab.

# LernReaktor – Übungsplattform für Laborant/innen EFZ Biologie

Web-App für die Berufsfachschule: Lernende stellen sich aus einer Aufgabendatenbank Übungsblätter
zusammen, drucken sie aus, lösen sie von Hand, laden Fotos hoch und erhalten von der Lehrperson eine
online korrigierte Rückmeldung. Lehrpersonen generieren aus derselben Datenbank Prüfungen.

## Funktionen

**Lernende**
- Übungsblatt nach **Themen**, **konkreten Lernzielen** und/oder **BiVo-Kompetenzzielen** (optional K-Stufe) zusammenstellen.
  Innerhalb eines Reiters gilt ODER, zwischen Reitern UND (z. B. qPCR *und* a.2.3 = qPCR-Rechenaufgaben).
- Die Auswahl bevorzugt noch nie bearbeitete Aufgaben und deckt die gewählten Ziele möglichst breit ab.
- PDF mit Kopf (Name, Klasse, Datum, Punkte), pro Aufgabe ein Antwortfeld (Linien, Karo oder leer, Höhe pro Aufgabe einstellbar).
- Fotos oder PDF-Scan hochladen (Handyfotos werden automatisch gedreht und verkleinert).
- Rückmeldung ansehen: Punkte, Kommentare, korrigierte Seiten, Rückmeldungs-PDF, Musterlösung (falls freigegeben).

**Lehrpersonen**
- Klassen anlegen, Lernenden-Zugänge per Namensliste erzeugen, Passwörter zurücksetzen.
- Beim Erstellen eines Übungsblatts wird das **Lösungsblatt** automatisch als PDF erzeugt und beim Lernenden abgelegt
  (Profil der lernenden Person → «Lösung»).
- **Online-Korrektur**: Stift, Textmarker, Text, Haken/Kreuz, Kreis, 4 Farben, Rückgängig; funktioniert mit Maus,
  Touch und Stift (iPad). Pro Aufgabe Punkte und Kommentar, Musterlösung einblendbar, Gesamtkommentar, Lösung freigeben.
- **Grafiken in Aufgaben**: beliebig viele Bilder pro Aufgabe (Foto, Diagramm, Screenshot, auch PDF-Seiten).
  Platzierung im Text mit `[[bild:1]]` auf einer eigenen Zeile; `[[bild:1]] [[bild:2]]` auf derselben Zeile = nebeneinander.
  Grösse pro Bild (volle, 2/3, halbe, 1/3, 1/4 Breite) oder pro Stelle (`[[bild:2|halb]]`), optionale Bildunterschrift.
  Bilder mit «nur in der Lösung» erscheinen nur auf Lösungsblättern (z. B. beschriftetes Gel). Nicht platzierte Bilder
  werden am Ende von Aufgabe bzw. Lösung angehängt. Knöpfe im Editor fügen die Marker an der Cursorposition ein.
- **Aufgabentypen**: freie Aufgabe, **Rechenaufgabe mit variablen Zahlen** (Variablen mit Bereich und Schritt,
  Ergebnisse per Formel, Platzhalter `{name}` in Text und Lösung – jedes Übungsblatt erhält eigene Zahlen, das
  Lösungsblatt rechnet mit denselben Werten), **Multiple Choice** (Optionen pro Blatt gemischt), **Zuordnung**
  (Beschreibungen gemischt, Buchstaben in der Lösung passend) und **Lückentext** (`{{Antwort}}`, optional Wortliste).
  Prüfungen verwenden pro Aufgabe eine Zahlenvariante für alle.
- **Komfortabler Editor**: Live-Vorschau von Aufgabenblatt und Lösung, Screenshots per Ctrl+V einfügen oder Bilder
  hineinziehen, Werkzeugleiste (fett, kursiv, hoch-/tiefgestellt, Listen, Teilaufgaben, Tabelle, Sonderzeichen) und
  Formel-Assistent für chemische Formeln (H2SO4 → H₂SO₄, SO42- → SO₄²⁻).
- **KI-Assistent (optional, im Standby)**: Entwurf aus Lernzielen (in jedem Aufgabentyp), Lösung prüfen
  (rechnet nach, auch mit konkreten Zahlenvarianten), Zuordnung vorschlagen (Thema, Lernziele, BiVo, K-Stufe) und
  Varianten erstellen (andere Zahlen, einfacher/anspruchsvoller, Englisch, anderer Typ). Wird erst aktiv, wenn
  `ANTHROPIC_API_KEY` gesetzt ist – siehe unten. Lernziele ohne Aufgabe haben in der Übersicht einen «+ Aufgabe»-Knopf.
- **Aufgabenverwaltung**: einfache Auszeichnung (fett, Listen, Tabellen, tief-/hochgestellt), Punkte, K-Stufe,
  Antwortfeld, Verwendung (*Übung & Prüfung*, *nur Übung*, *nur Prüfung* – Letztere sehen Lernende nie), PDF-Vorschau,
  Duplizieren als Variante, JSON-Export/-Import zum Austausch zwischen Lehrpersonen (ohne Bilddateien).
- **Lernziele**: Import direkt aus dem PDF «Lernziele konkret» (oder eingefügtem Text). Erkannt werden Einträge wie
  `14. Ich kann … (a.4.1, a.4.2, K2)`. Übersicht zeigt, welche Lernziele noch **keine** Aufgabe haben.
- **BiVo-Kompetenzen**: Import aus der Excel-Liste; Übersicht mit Abdeckung durch Aufgaben.
- **Prüfungsgenerator**: Parameter Themen, abzudeckende Lernziele/Kompetenzziele, Ziel-Punktzahl, max. Anzahl Aufgaben,
  K-Stufen, «nur geheime Prüfungsaufgaben», «von der Klasse bereits geübte Aufgaben ausschliessen».
  Danach Aufgaben manuell hinzufügen/entfernen/umsortieren; Abdeckungsbericht; Prüfungs- und Lösungs-PDF.

Mitgeliefert: alle 71 Leistungsziele aus `Kompetenzen_BiVo.xlsx`, die 33 qPCR-Lernziele aus
`Lernziele_konkret_molek1.pdf` und 19 Beispielaufgaben (qPCR, Neubauer-Zählkammer) mit Musterlösungen.
**Bitte die Beispielaufgaben fachlich prüfen**, bevor sie im Unterricht eingesetzt werden.

## Schnellstart

```bash
python3 -m venv .venv
.venv/bin/pip install -r requirements.txt
.venv/bin/flask --app run init-db --demo
.venv/bin/flask --app run run
```

Dann http://127.0.0.1:5000 öffnen. Demo-Zugänge: `lp` / `lp-demo-2026` (Lehrperson), `lea` bzw. `noah` / `lernen-2026`.

Eigenes Lehrpersonen-Konto: `.venv/bin/flask --app run create-lp mmuster "Maria Muster"`

Tests: `.venv/bin/python -m pytest`

## Aufbau

| Datei | Inhalt |
|---|---|
| `app/models.py` | Datenmodell (Bereich → Handlungskompetenz → Leistungsziel; Thema → Lernziel; Aufgabe; Übungsblatt, Abgabe, Seite; Prüfung) |
| `app/importers.py` | Excel-Import BiVo, Lernziel-Parser (Text/PDF), Aufgaben-JSON |
| `app/aufgabentypen.py` | Aufgabentypen, variable Zahlen (sichere Formelauswertung), Rendering pro Seed |
| `app/ki.py` | KI-Assistent (Claude API, strukturierte Antworten, Verbrauchsprotokoll) |
| `app/selection.py` | Aufgabenauswahl für Übungsblätter, Prüfungsgenerator (Greedy-Abdeckung + Auffüllen) |
| `app/pdfgen.py` | Alle PDFs (ReportLab) inkl. Antwortfelder und Auszeichnungssprache |
| `app/lernende.py`, `app/lp.py`, `app/auth.py` | Routen für Lernende, Lehrpersonen, Login |
| `app/static/korrektur.js` | Annotationswerkzeug (Canvas, Pointer Events) |
| `app/static/editor.js`, `aufgabentypen.js`, `ki.js` | Aufgaben-Editor: Werkzeugleiste, Bilder, Live-Vorschau, Typen, KI |
| `app/seed_data/` | Ausgangsdaten (Excel, Lernziele, Beispielaufgaben) |

Daten liegen in `instance/` (SQLite-Datenbank `lernreaktor.sqlite`, Uploads in `instance/dateien/`).
Für ein Backup genügt es, diesen Ordner zu sichern.

## Sicherheit

- Passwörter als scrypt-Hash; Startpasswörter (Klassenliste, Zurücksetzen) müssen bei der ersten Anmeldung geändert werden.
- Login-Sperre: nach 5 Fehlversuchen pro Konto bzw. 20 pro IP-Adresse 15 Minuten gesperrt.
- Neue Sitzung bei jeder Anmeldung, Abmeldung nach 60 Minuten Inaktivität (`INAKTIV_MINUTEN`), höchstens 12 Stunden.
- CSRF-Schutz für alle Formulare und Anfragen (Vergleich in konstanter Zeit).
- Strenge Content-Security-Policy (keine Inline-Skripte, keine externen Quellen), Schutz vor Einbettung (Clickjacking),
  `nosniff`, keine Speicherung persönlicher Seiten im Browser-Cache. Schriften werden lokal ausgeliefert.
- Zugriffskontrolle serverseitig: Lehrpersonen sehen nur Lernende ihrer Klassen, Lernende nur eigene Blätter.
- Uploads werden neu kodiert (entfernt u. a. GPS-Daten aus Handyfotos); Formeln werden nur über eine Whitelist ausgewertet.
- Abhängigkeiten prüfen: `pip install pip-audit && pip-audit -r requirements.txt`

## Installation auf einem Server

Für Ubuntu (26.04/24.04) mit PostgreSQL, nginx und HTTPS gibt es ein Installationspaket in `deploy/`:
**[deploy/INSTALLATION.md](deploy/INSTALLATION.md)** – Installation in drei Befehlen, Domain später per Skript,
Updates, tägliche Sicherungen und Wiederherstellung.

## Betrieb an der Schule (Hinweise)

- Produktiv mit einem WSGI-Server hinter HTTPS betreiben, z. B. `pip install gunicorn` und
  `gunicorn -w 3 --timeout 180 -b 127.0.0.1:8000 run:app` hinter nginx/Caddy. Nie den Flask-Entwicklungsserver öffnen.
- `SECRET_KEY` als Umgebungsvariable setzen (sonst wird einer in `instance/secret_key` erzeugt).
- **Immer über HTTPS** betreiben und `LERNREAKTOR_HTTPS=1` setzen (Cookies nur über HTTPS, HSTS). Hinter nginx/Caddy
  zusätzlich `LERNREAKTOR_PROXY=1`, damit IP-Adressen (Login-Sperre) und Protokoll richtig erkannt werden.
- Für mehrere Lehrpersonen gleichzeitig: `DATABASE_URL` auf PostgreSQL zeigen lassen (SQLAlchemy, keine Codeänderung nötig).
- Datenschutz (revDSG): Es werden Namen, Leistungen und Fotos von Handschrift gespeichert. Hosting in der Schweiz
  bzw. auf schuleigener Infrastruktur, Zugriff nur für zuständige Lehrpersonen (ist so umgesetzt: eine LP sieht nur
  Lernende ihrer Klassen), Löschkonzept nach Lehrabschluss mit der Schulleitung klären.

## KI-Assistent einschalten

Der Assistent nutzt die **Claude API** (Abrechnung pro Nutzung über die Claude Console, unabhängig von einem
Claude-Abo). Ohne Schlüssel bleibt er ausgeschaltet und die App funktioniert unverändert.

1. In der Claude Console (platform.claude.com) ein Konto der Schule anlegen, Guthaben aufladen, einen API-Schlüssel
   erstellen und ein monatliches Ausgabenlimit setzen.
2. Auf dem Server `ANTHROPIC_API_KEY=...` als Umgebungsvariable setzen und die App neu starten.
3. Optional: `KI_MODELL` (Standard `claude-opus-5-5`), `KI_AKTIV=0` (vorübergehend aus),
   `KI_PREIS_INPUT` / `KI_PREIS_OUTPUT` / `KI_PREIS_CACHE_LESEN` (USD pro Million Tokens) für die Kostenschätzung.

Unter **KI** in der Navigation stehen Status, Verbrauch und geschätzte Kosten. Übermittelt werden nur
Aufgabeninhalte und Lernziele, keine Daten von Lernenden. Eine KI-Anfrage dauert typischerweise 10–60 Sekunden;
beim Betrieb mit gunicorn deshalb `--timeout 180` setzen.

## Mögliche nächste Schritte

- Visueller Editor (Tiptap) mit HTML-zu-PDF-Ausgabe (WeasyPrint), damit Vorschau und Druck identisch sind.
- Anmeldung über Schul-Login (Microsoft 365 / Edulog) statt eigener Passwörter.
- QR-Code auf jedem Blatt, damit Uploads automatisch zugeordnet und Seiten sortiert werden.
- Prüfungen ebenfalls hochladen und online korrigieren (gleiches Werkzeug wie bei Übungsblättern).
- Lernstand pro Lernziel über die Zeit (Heatmap pro Klasse).

## Lizenzen der Schriften

`app/static/fonts/`: Liberation Sans (SIL Open Font License) und DejaVu Sans (freie Lizenz) für die PDFs;
`app/static/fonts/web/`: Inter und Source Serif 4 (beide SIL Open Font License) für die Weboberfläche.
Siehe die LICENSE-Dateien in diesen Ordnern.

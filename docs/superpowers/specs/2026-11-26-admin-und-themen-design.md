# BiVo-Import nur für Admins · Themen zuerst anlegen, dann Lernziele importieren

Stand: 2026-11-26 · kleine Änderung (Kurzdesign)

## Warum

Die BiVo-Kompetenzziele (Bildungsverordnung) ändern sich nicht; Lehrpersonen sollen sie nicht neu einlesen
können. Lernziele gehören immer zu einem bewusst angelegten Thema – Tippfehler im Themennamen beim Import sollen
keine neuen Themen erzeugen.

## Ziele

**1. Admin-Recht (Variante A: Flag am Lehrpersonen-Konto)**
- Neue Spalte `user.ist_admin` (Boolean, Standard falsch), über `SPALTEN_NACHTRAG` automatisch nachgerüstet.
- Serverbefehl `flask set-admin <benutzername>` (mit `--entziehen` zum Zurücknehmen); nur für Konten mit Rolle «lp».
  Im Container: `docker exec lernreaktor flask --app run set-admin <name>`.
- Seite «Kompetenzen BiVo»: Lesen weiterhin für alle Lehrpersonen; das Formular «Kompetenzliste neu einlesen»
  sehen nur Admins; ein POST von Nicht-Admins wird mit 403 abgewiesen.
- Demo-Lehrperson `lp` ist **kein** Admin.

**2. Themen zuerst, dann importieren**
- Seite «Lernziele»: oben ein Formular «Neues Thema» (Name, Beschreibung). Doppelter Name → Fehlermeldung.
- Import-Seite: erstes Feld «Thema» ist eine **Auswahlliste der bestehenden Themen** (Pflicht) statt Freitext.
  Der Import legt keine neuen Themen mehr an.
- Je Thema auf der Lernziele-Seite ein Link «Lernziele importieren», der das Thema vorwählt (`?thema=<id>`);
  der Knopf oben bleibt (ohne Vorwahl).
- Gibt es noch kein Thema, zeigt die Import-Seite statt des Formulars den Hinweis, zuerst ein Thema anzulegen.
- Das Feld «Neues Thema anlegen» im Aufgabenformular bleibt unverändert.

## Nicht-Ziele

- Keine eigene Rolle «admin», keine Admin-Verwaltung in der App.
- Seed (`init-db`) liest die BiVo-Liste weiterhin aus der mitgelieferten Datei ein.

## Ansätze (gewählt: A)

- **A – Admin-Flag am Lehrpersonen-Konto, per Serverbefehl gesetzt.** Klein; Admin bleibt normale Lehrperson. *Gewählt.*
- B – eigene Rolle «admin»: sauberer bei getrennten Personen, aber mehr Menüs, Rechte, Tests.
- C – kein Upload in der App, nur Serverbefehl: am einfachsten, aber jede Änderung braucht Serverzugang.

## Dem Umsetzenden überlassen

Routen-/Templatenamen, Platzierung der Formulare im Detail, Tests in `tests/test_lernziele.py` bzw. neuer Datei.

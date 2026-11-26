# Lernziele ↔ Kompetenzziele in der Auswahl verknüpft · K-Stufen-Filter als Admin-Option

Stand: 2026-11-26 · kleine Änderung (Kurzdesign)

## Warum

Lernziele beruhen auf BiVo-Kompetenzzielen; in der Aufgabenauswahl (Übungsblatt der Lernenden, Prüfung der
Lehrperson) sollen beide Reiter deshalb zusammenpassen. Der K-Stufen-Filter wird selten gebraucht und soll nur
erscheinen, wenn ein Admin ihn einschaltet.

## Ziele

**1. Gegenseitiges Ankreuzen (Übungsblatt `lernende/neu` und Prüfung `lp/pruefungen/neu`)**
- Lernziel an → seine Kompetenzziele an. Lernziel aus → seine Kompetenzziele aus, ausser ein anderes angekreuztes
  Lernziel bringt sie mit.
- Kompetenzziel an → alle Lernziele, die darauf beruhen, an. Kompetenzziel aus → diese Lernziele aus.
- Keine Kettenreaktion: das Ankreuzen eines Kompetenzziels kreuzt die *übrigen* Codes der mitgewählten Lernziele
  nicht an.
- Aufgabenformular bleibt einseitig (Lernziel → Kompetenzziele), wie bisher.

**2. Lernziele und Kompetenzziele zählen als eine Gruppe (ODER)**
- Übungsblatt-Suche und Trefferzahl (`selection.filter_aufgaben`): Aufgaben, die eines der gewählten Lernziele
  **oder** eines der gewählten Kompetenzziele haben. Themen und (falls eingeschaltet) K-Stufen bleiben UND.
- Prüfungszusammenstellung verhält sich bereits so – unverändert.
- Erklärtext auf der Übungsblatt-Seite entsprechend anpassen.

**3. K-Stufen-Filter als Option (Variante A: nur der Filter)**
- Neue Tabelle für Einstellungen (Schlüssel/Wert), Eintrag `k_stufen_filter`, Standard **aus**.
- Neue Seite «Einstellungen» (Menü, nur für Admins, sonst 403) mit Schalter «K-Stufen-Filter in der
  Aufgabenauswahl anzeigen».
- Aus: Filter in Übungsblatt- und Prüfungsauswahl ausgeblendet; übermittelte K-Stufen werden serverseitig ignoriert.
- K-Stufen von Aufgaben, Lernzielen und BiVo-Liste bleiben überall unverändert sichtbar und erfassbar.

## Nicht-Ziele

- Keine Änderung der Prüfungslogik, keine K-Stufen-Ausblendung ausserhalb des Filters.

## Ansätze

- Verknüpfung: **gemeinsame ODER-Gruppe (gewählt)** · nur einseitig ankreuzen · beidseitig mit UND (verkleinert
  Treffer: Aufgaben nur mit BiVo-Code ohne Lernziel fielen weg).
- Einstellung speichern: **Tabelle in der Datenbank (gewählt)**, umschaltbar in der App · Umgebungsvariable
  (bräuchte Neustart und Serverzugang) · Datei im Instanzordner (nicht in der App umschaltbar, im Container umständlich).

## Dem Umsetzenden überlassen

Namen von Modell/Route/Template, Darstellung der Einstellungsseite, Tests.

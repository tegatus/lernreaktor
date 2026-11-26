# Lernziele: Formular mit Pflicht-Verknüpfung zu BiVo-Kompetenzzielen

Stand: 2026-11-26 · kleine Änderung (Kurzdesign)

## Warum

Jedes Lernziel muss auf mindestens einem BiVo-Leistungsziel (Kompetenzziel) beruhen. Heute entstehen
Lernziele nur über den Text-Import; unbekannte Codes führen zu Lernzielen ohne Verknüpfung, und einzelne
Lernziele lassen sich in der App weder anlegen noch korrigieren.

## Ziele

- Formular zum **Anlegen und Bearbeiten** einzelner Lernziele (Thema, Bereich, Nummer, Text, K-Stufe,
  BiVo-Kompetenzziele). **Mindestens ein** Kompetenzziel ist Pflicht, mehrere sind möglich.
- Löschen eines Lernziels nur, wenn keine Aufgabe es verwendet (sonst Hinweis, welche).
- Lernziele ohne Kompetenzziel werden in der Liste rot markiert («kein BiVo-Ziel»).
- **Import:** Einträge ohne gültigen BiVo-Code werden nicht übernommen (Warnung in der Vorschau);
  einzelne unbekannte Codes bei sonst gültigen Einträgen bleiben ein Hinweis.
- **Aufgabenformular:** Beim Ankreuzen eines Lernziels werden dessen Kompetenzziele sofort mit angekreuzt
  (JavaScript). Serverseitig bleibt die bisherige Ergänzung beim Speichern.
- **Weitergabe an bestehende Aufgaben (Variante A):** Ändern sich die Kompetenzziele eines Lernziels,
  werden alle Aufgaben mit diesem Lernziel nachgeführt: neue Codes ergänzt; entfernte Codes entfernt,
  ausser ein anderes Lernziel der Aufgabe bringt den Code noch mit. Das Formular meldet, wie viele
  Aufgaben angepasst wurden.

## Nicht-Ziele

- Keine Unterscheidung «direkt gewählt» vs. «über Lernziel» in der Datenbank (bewusst in Kauf genommen:
  ein früher von Hand gesetzter Code kann bei Variante A mit entfernt werden).
- Keine Änderung an Themen-Verwaltung, Kompetenz-Import oder Agent-Schnittstelle.

## Ansätze (gewählt: A)

- **A – beim Speichern nachführen:** gespeicherte Codes der Aufgaben werden aktualisiert. Kleine Änderung,
  alle bestehenden Auswertungen bleiben unverändert. *Gewählt.*
- **B – Codes immer live aus den Lernzielen ableiten:** nie veraltet, aber Auswahl, Kompetenzstand,
  Prüfungen und Agent-Schnittstelle lesen die gespeicherten Codes → grosser Umbau.
- **C – bestehende Aufgaben nicht anfassen:** einfachste Lösung, hinterlässt aber veraltete Zuordnungen.

## Festgelegtes

- Bereich wird aus dem ersten gewählten Kompetenzziel vorgeschlagen, die Nummer als nächste freie Nummer
  im Thema+Bereich; beides überschreibbar. Thema+Bereich+Nummer muss eindeutig bleiben.
- Einstieg: «+ Lernziel» je Thema und «Bearbeiten» je Zeile auf der Seite Lernziele (nur Rolle «lp»).
- Kompetenzziel-Auswahl gruppiert nach Handlungskompetenz (wie im Aufgabenformular).

## Dem Umsetzenden überlassen

Routen-/Templatenamen, Darstellung der Kompetenzziel-Auswahl im Detail, Tests (pytest in
`tests/test_app.py`).

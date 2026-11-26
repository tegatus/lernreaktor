"""Konkrete Lernziele: Nummernvergabe, Verknüpfung mit BiVo-Kompetenzzielen und deren Weitergabe an Aufgaben."""
from sqlalchemy import func

from .models import Aufgabe, Leistungsziel, Lernziel, TheorieKapitel, db


def naechste_nummer(thema_id, bereich):
    """Nächste freie Nummer im Thema+Bereich (höchste + 1, sonst 1)."""
    hoechste = (db.session.query(func.max(Lernziel.nummer))
                .filter(Lernziel.thema_id == thema_id, Lernziel.bereich == bereich).scalar())
    return (hoechste or 0) + 1


def aufgaben_mit(lz):
    """Alle Aufgaben (auch inaktive), die dieses Lernziel verwenden."""
    if lz.id is None:
        return []
    return Aufgabe.query.filter(Aufgabe.lernziele.any(Lernziel.id == lz.id)).order_by(Aufgabe.id).all()


def kompetenzziele_setzen(lz, codes):
    """Setzt die BiVo-Kompetenzziele des Lernziels (unbekannte Codes werden ignoriert) und führt die Aufgaben nach,
    die das Lernziel verwenden: neue Codes kommen hinzu, entfernte verschwinden – ausser ein anderes Lernziel der
    Aufgabe bringt den Code ebenfalls mit. Gibt die Anzahl geänderter Aufgaben zurück. Kein Commit."""
    alt = {l.code for l in lz.leistungsziele}
    lz.leistungsziele = (Leistungsziel.query.filter(Leistungsziel.code.in_(set(codes)))
                         .order_by(Leistungsziel.sort).all())
    neu = {l.code for l in lz.leistungsziele}
    if alt == neu:
        return 0
    geaendert = 0
    for a in aufgaben_mit(lz):
        andere = {l.code for x in a.lernziele if x is not lz for l in x.leistungsziele}
        cur = {l.code for l in a.leistungsziele}
        soll = (cur | neu) - ((alt - neu) - andere)
        if soll != cur:
            a.leistungsziele = Leistungsziel.query.filter(Leistungsziel.code.in_(soll)).all()
            geaendert += 1
    return geaendert


def lernziel_loeschen(lz):
    """Löscht das Lernziel, sofern keine Aufgabe es verwendet; Verknüpfungen zu Theoriekapiteln werden entfernt.
    Gibt die verwendenden Aufgaben zurück (leer = gelöscht). Kein Commit."""
    verwendet = aufgaben_mit(lz)
    if verwendet:
        return verwendet
    verknuepfungen_loesen(lz)
    db.session.delete(lz)
    return []


def verknuepfungen_loesen(lz, aufgaben=False):
    """Entfernt die Verknüpfungen zu Theoriekapiteln (und mit aufgaben=True auch zu Aufgaben), damit das Lernziel
    ohne Fremdschlüssel-Fehler gelöscht werden kann. Die BiVo-Codes der Aufgaben bleiben stehen. Kein Commit."""
    for k in TheorieKapitel.query.filter(TheorieKapitel.lernziele.any(Lernziel.id == lz.id)):
        k.lernziele.remove(lz)
    if aufgaben:
        for a in aufgaben_mit(lz):
            a.lernziele.remove(lz)

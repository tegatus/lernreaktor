"""Einstellungen der Installation (von Admins in der App umschaltbar), gespeichert in der Tabelle «einstellung»."""
from .models import Einstellung, db

STANDARD = {
    "k_stufen_filter": False,  # K-Stufen-Filter in der Aufgabenauswahl (Übungsblatt, Prüfung) anzeigen
}


def einstellung(name):
    """Aktueller Wert (Schalter als bool); ohne gespeicherten Eintrag gilt der Standardwert."""
    e = db.session.get(Einstellung, name)
    if e is None:
        return STANDARD[name]
    return e.wert == "1" if isinstance(STANDARD[name], bool) else e.wert


def einstellung_setzen(name, wert):
    """Speichert den Wert (kein Commit)."""
    if name not in STANDARD:
        raise KeyError(name)
    e = db.session.get(Einstellung, name) or Einstellung(schluessel=name)
    e.wert = ("1" if wert else "0") if isinstance(STANDARD[name], bool) else str(wert)
    db.session.add(e)

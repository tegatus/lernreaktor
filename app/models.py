"""Datenmodell der Übungsplattform.

Taxonomie:
  Bereich (a, b, e, …) → Handlungskompetenz (a.1) → Leistungsziel (a.1.1, K-Stufe)   [Bildungsverordnung]
  Thema (qPCR, Neubauer-Zählkammer, …) → Lernziel (konkret, "Ich kann …")  ↔ Leistungsziele
  Aufgabe ↔ Themen, Leistungsziele, Lernziele
"""
import json
import re
from datetime import datetime, timezone

from flask_login import UserMixin
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import check_password_hash, generate_password_hash

db = SQLAlchemy()


def now():
    return datetime.now(timezone.utc).replace(tzinfo=None)


# ---------------------------------------------------------------- Benutzer

class Klasse(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    lp_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    lp = db.relationship("User", foreign_keys=[lp_id], backref="eigene_klassen")
    lernende = db.relationship("User", foreign_keys="User.klasse_id", back_populates="klasse",
                               order_by="User.anzeigename")


class User(UserMixin, db.Model):
    id = db.Column(db.Integer, primary_key=True)
    benutzername = db.Column(db.String(80), unique=True, nullable=False)
    anzeigename = db.Column(db.String(120), nullable=False)
    passwort_hash = db.Column(db.String(255), nullable=False)
    rolle = db.Column(db.String(20), nullable=False, default="lernende")  # "lp" | "lernende" | "reviewer"
    # Klasse ↔ Lehrperson verweisen gegenseitig aufeinander: benannte, nachträglich angelegte Fremdschlüssel,
    # damit PostgreSQL die Tabellen in beliebiger Reihenfolge anlegen und löschen kann
    klasse_id = db.Column(db.Integer, db.ForeignKey("klasse.id", use_alter=True, name="fk_user_klasse"))
    klasse = db.relationship("Klasse", foreign_keys=[klasse_id], back_populates="lernende")
    aktiv = db.Column(db.Boolean, default=True, nullable=False)
    passwort_aendern = db.Column(db.Boolean, default=False, nullable=False)  # nach generiertem Startpasswort
    ist_admin = db.Column(db.Boolean, default=False, nullable=False)  # Lehrperson mit Admin-Recht (flask set-admin)

    def set_passwort(self, pw):
        self.passwort_hash = generate_password_hash(pw)

    def check_passwort(self, pw):
        return check_password_hash(self.passwort_hash, pw)

    @property
    def ist_lp(self):
        return self.rolle == "lp"

    @property
    def ist_reviewer(self):
        return self.rolle == "reviewer"

    @property
    def ist_lernende(self):
        return self.rolle == "lernende"

    @property
    def is_active(self):
        return self.aktiv

    def betreut(self, lernende):
        """True, wenn diese LP die lernende Person (über eine Klasse) betreut."""
        return self.ist_lp and lernende.klasse is not None and lernende.klasse.lp_id == self.id


# ---------------------------------------------------------------- Bildungsverordnung

class Bereich(db.Model):
    code = db.Column(db.String(4), primary_key=True)  # "a"
    titel = db.Column(db.String(255), nullable=False)
    handlungskompetenzen = db.relationship("Handlungskompetenz", back_populates="bereich",
                                           order_by="Handlungskompetenz.sort")


class Handlungskompetenz(db.Model):
    code = db.Column(db.String(10), primary_key=True)  # "a.1"
    titel = db.Column(db.Text, nullable=False)
    sort = db.Column(db.Integer, default=0)
    bereich_code = db.Column(db.String(4), db.ForeignKey("bereich.code"), nullable=False)
    bereich = db.relationship("Bereich", back_populates="handlungskompetenzen")
    leistungsziele = db.relationship("Leistungsziel", back_populates="handlungskompetenz",
                                     order_by="Leistungsziel.sort")


class Leistungsziel(db.Model):
    """Kompetenzziel gemäss BiVo / Bildungsplan, z. B. a.1.1 (K2)."""
    code = db.Column(db.String(12), primary_key=True)  # "a.1.1"
    text = db.Column(db.Text, nullable=False)
    k_stufe = db.Column(db.Integer)
    sort = db.Column(db.Integer, default=0)
    hk_code = db.Column(db.String(10), db.ForeignKey("handlungskompetenz.code"), nullable=False)
    handlungskompetenz = db.relationship("Handlungskompetenz", back_populates="leistungsziele")


# ---------------------------------------------------------------- Themen & Lernziele

class Thema(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), unique=True, nullable=False)
    beschreibung = db.Column(db.Text, default="")
    lernziele = db.relationship("Lernziel", back_populates="thema", order_by="[Lernziel.bereich, Lernziel.nummer]",
                                cascade="all, delete-orphan")


lernziel_leistungsziel = db.Table(
    "lernziel_leistungsziel",
    db.Column("lernziel_id", db.Integer, db.ForeignKey("lernziel.id"), primary_key=True),
    db.Column("leistungsziel_code", db.String(12), db.ForeignKey("leistungsziel.code"), primary_key=True),
)


class Lernziel(db.Model):
    """Konkretes Lernziel ("Ich kann …"), basiert auf einem oder mehreren Leistungszielen."""
    id = db.Column(db.Integer, primary_key=True)
    thema_id = db.Column(db.Integer, db.ForeignKey("thema.id"), nullable=False)
    thema = db.relationship("Thema", back_populates="lernziele")
    bereich = db.Column(db.String(4), nullable=False)  # "a"
    nummer = db.Column(db.Integer, nullable=False)
    text = db.Column(db.Text, nullable=False)
    k_stufe = db.Column(db.Integer)
    leistungsziele = db.relationship("Leistungsziel", secondary=lernziel_leistungsziel,
                                     order_by="Leistungsziel.sort")

    @property
    def kuerzel(self):
        return f"{self.bereich}{self.nummer}"

    @property
    def label(self):
        return f"{self.thema.name} {self.kuerzel}"


# ---------------------------------------------------------------- Aufgaben

aufgabe_thema = db.Table(
    "aufgabe_thema",
    db.Column("aufgabe_id", db.Integer, db.ForeignKey("aufgabe.id"), primary_key=True),
    db.Column("thema_id", db.Integer, db.ForeignKey("thema.id"), primary_key=True),
)
aufgabe_leistungsziel = db.Table(
    "aufgabe_leistungsziel",
    db.Column("aufgabe_id", db.Integer, db.ForeignKey("aufgabe.id"), primary_key=True),
    db.Column("leistungsziel_code", db.String(12), db.ForeignKey("leistungsziel.code"), primary_key=True),
)
aufgabe_lernziel = db.Table(
    "aufgabe_lernziel",
    db.Column("aufgabe_id", db.Integer, db.ForeignKey("aufgabe.id"), primary_key=True),
    db.Column("lernziel_id", db.Integer, db.ForeignKey("lernziel.id"), primary_key=True),
)

ANTWORTFORMATE = {"linien": "Linien", "karo": "Karo (Rechnungen)", "leer": "Leeres Feld", "keins": "Kein Antwortfeld"}
VERWENDUNGEN = {"beide": "Übung & Prüfung", "uebung": "Nur Übung", "pruefung": "Nur Prüfung (geheim)"}


class Aufgabe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titel = db.Column(db.String(200), nullable=False)
    text = db.Column(db.Text, nullable=False)       # einfache Auszeichnung, siehe pdfgen.markup
    loesung = db.Column(db.Text, nullable=False, default="")
    punkte = db.Column(db.Float, nullable=False, default=2)
    k_stufe = db.Column(db.Integer)
    schwierigkeit = db.Column(db.Integer, default=2)  # 1 leicht – 3 schwer
    antwortformat = db.Column(db.String(10), default="linien")
    antwortraum_cm = db.Column(db.Float, default=5.0)
    verwendung = db.Column(db.String(10), default="beide")
    bild = db.Column(db.String(255))  # veraltet (früher: ein Bild pro Aufgabe) – siehe AufgabeBild
    typ = db.Column(db.String(12), default="frei", nullable=False)   # siehe aufgabentypen.TYPEN
    daten = db.Column(db.Text, default="{}", nullable=False)         # strukturierte Daten des Typs (JSON)
    aktiv = db.Column(db.Boolean, default=True, nullable=False)
    erstellt_am = db.Column(db.DateTime, default=now)
    geaendert_am = db.Column(db.DateTime, default=now, onupdate=now)

    themen = db.relationship("Thema", secondary=aufgabe_thema, order_by="Thema.name")
    leistungsziele = db.relationship("Leistungsziel", secondary=aufgabe_leistungsziel, order_by="Leistungsziel.sort")
    lernziele = db.relationship("Lernziel", secondary=aufgabe_lernziel)
    bilder = db.relationship("AufgabeBild", order_by="AufgabeBild.nr", cascade="all, delete-orphan",
                             back_populates="aufgabe")
    kapitel = db.relationship("TheorieKapitel", secondary="aufgabe_kapitel", back_populates="aufgaben")

    def bild_nr(self, nr):
        return next((b for b in self.bilder if b.nr == nr), None)

    def to_dict(self):
        return {
            "titel": self.titel, "text": self.text, "loesung": self.loesung, "punkte": self.punkte,
            "k_stufe": self.k_stufe, "schwierigkeit": self.schwierigkeit, "antwortformat": self.antwortformat,
            "antwortraum_cm": self.antwortraum_cm, "verwendung": self.verwendung,
            "typ": self.typ or "frei", "daten": json.loads(self.daten or "{}"),
            "themen": [t.name for t in self.themen],
            "leistungsziele": [l.code for l in self.leistungsziele],
            "lernziele": [f"{l.thema.name}|{l.kuerzel}" for l in self.lernziele],
        }


BILDGROESSEN = {"voll": ("Volle Breite", 1.0), "zweidrittel": ("2/3 Breite", 2 / 3), "halb": ("Halbe Breite", 0.5),
                "drittel": ("1/3 Breite", 1 / 3), "viertel": ("1/4 Breite", 0.25)}


class AufgabeBild(db.Model):
    """Grafik zu einer Aufgabe. Platzierung im Text mit [[bild:NR]] (optional [[bild:NR|halb]]).

    nur_loesung=True: erscheint nur auf Lösungsblättern, nie auf dem Aufgabenblatt.
    Nicht referenzierte Bilder werden am Ende des Aufgabentexts bzw. der Lösung angehängt.
    """
    id = db.Column(db.Integer, primary_key=True)
    aufgabe_id = db.Column(db.Integer, db.ForeignKey("aufgabe.id"), nullable=False)
    aufgabe = db.relationship("Aufgabe", back_populates="bilder")
    nr = db.Column(db.Integer, nullable=False)          # stabil, wird beim Löschen nicht neu vergeben
    datei = db.Column(db.String(255), nullable=False)
    groesse = db.Column(db.String(12), default="voll")
    nur_loesung = db.Column(db.Boolean, default=False, nullable=False)
    beschriftung = db.Column(db.String(300), default="")

    @property
    def marker(self):
        return f"[[bild:{self.nr}]]"

    @property
    def breite_anteil(self):
        return BILDGROESSEN.get(self.groesse, BILDGROESSEN["voll"])[1]


# ---------------------------------------------------------------- Theorie

aufgabe_kapitel = db.Table(
    "aufgabe_kapitel",
    db.Column("aufgabe_id", db.Integer, db.ForeignKey("aufgabe.id"), primary_key=True),
    db.Column("kapitel_id", db.Integer, db.ForeignKey("theorie_kapitel.id"), primary_key=True),
)
kapitel_lernziel = db.Table(
    "kapitel_lernziel",
    db.Column("kapitel_id", db.Integer, db.ForeignKey("theorie_kapitel.id"), primary_key=True),
    db.Column("lernziel_id", db.Integer, db.ForeignKey("lernziel.id"), primary_key=True),
)


def _natuerlich(nummer):
    """Sortierschlüssel für Kapitelnummern: 2 < 10, 3.2 < 3.10."""
    return [(0, int(t), "") if t.isdigit() else (1, 0, t.lower()) for t in re.split(r"(\d+)", nummer or "") if t]


class TheorieDokument(db.Model):
    """Ein Theorieteil (z. B. ein Skript) mit Kapiteln."""
    id = db.Column(db.Integer, primary_key=True)
    titel = db.Column(db.String(200), nullable=False)
    beschreibung = db.Column(db.Text, default="")
    kapitel = db.relationship("TheorieKapitel", back_populates="dokument", cascade="all, delete-orphan")

    @property
    def kapitel_sortiert(self):
        return sorted(self.kapitel, key=lambda k: (_natuerlich(k.nummer), k.titel.lower()))


class TheorieKapitel(db.Model):
    """Ein Kapitel Theorie in der Aufgaben-Auszeichnung (Bilder mit [[bild:NR]], Zwischentitel mit «## »)."""
    id = db.Column(db.Integer, primary_key=True)
    dokument_id = db.Column(db.Integer, db.ForeignKey("theorie_dokument.id"), nullable=False)
    dokument = db.relationship("TheorieDokument", back_populates="kapitel")
    nummer = db.Column(db.String(20), default="")       # z. B. "3.2", bestimmt die Reihenfolge
    titel = db.Column(db.String(200), nullable=False)
    text = db.Column(db.Text, nullable=False, default="")
    sichtbar = db.Column(db.Boolean, default=True, nullable=False)  # False = Entwurf, nur für Lehrpersonen
    geaendert_am = db.Column(db.DateTime, default=now, onupdate=now)
    bilder = db.relationship("KapitelBild", order_by="KapitelBild.nr", cascade="all, delete-orphan",
                             back_populates="kapitel")
    lernziele = db.relationship("Lernziel", secondary=kapitel_lernziel)
    aufgaben = db.relationship("Aufgabe", secondary=aufgabe_kapitel, back_populates="kapitel")
    review_kommentare = db.relationship("ReviewKommentar", back_populates="kapitel", cascade="all, delete-orphan")

    @property
    def label(self):
        return f"{self.nummer} {self.titel}".strip()


class KapitelBild(db.Model):
    """Grafik in einem Theoriekapitel (wie AufgabeBild, ohne «nur Lösung»)."""
    id = db.Column(db.Integer, primary_key=True)
    kapitel_id = db.Column(db.Integer, db.ForeignKey("theorie_kapitel.id"), nullable=False)
    kapitel = db.relationship("TheorieKapitel", back_populates="bilder")
    nr = db.Column(db.Integer, nullable=False)
    datei = db.Column(db.String(255), nullable=False)
    groesse = db.Column(db.String(12), default="voll")
    beschriftung = db.Column(db.String(300), default="")
    nur_loesung = False

    @property
    def marker(self):
        return f"[[bild:{self.nr}]]"


def migriere_einzelbilder():
    """Übernimmt das frühere Einzelbild (Aufgabe.bild) als Bild Nr. 1."""
    for a in Aufgabe.query.filter(Aufgabe.bild.isnot(None)).all():
        if not a.bilder:
            a.bilder.append(AufgabeBild(nr=1, datei=a.bild, groesse="voll"))
        a.bild = None
    db.session.commit()


# ---------------------------------------------------------------- Übungsblätter der Lernenden

class Uebungsblatt(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    lernende_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    lernende = db.relationship("User", backref=db.backref("uebungsblaetter", order_by="Uebungsblatt.erstellt_am.desc()"))
    titel = db.Column(db.String(200), nullable=False)
    auswahl = db.Column(db.Text, default="")  # lesbare Beschreibung der Filter
    erstellt_am = db.Column(db.DateTime, default=now)
    status = db.Column(db.String(20), default="offen")  # offen | eingereicht | korrigiert
    loesung_freigegeben = db.Column(db.Boolean, default=False)
    gesamtkommentar = db.Column(db.Text, default="")
    korrigiert_am = db.Column(db.DateTime)
    aufgaben = db.relationship("BlattAufgabe", order_by="BlattAufgabe.position", cascade="all, delete-orphan",
                               back_populates="blatt")
    abgaben = db.relationship("Abgabe", order_by="Abgabe.hochgeladen_am", cascade="all, delete-orphan",
                              back_populates="blatt")

    @property
    def code(self):
        return f"UE-{self.id:05d}"

    @property
    def max_punkte(self):
        return sum(a.aufgabe.punkte for a in self.aufgaben)

    @property
    def erreichte_punkte(self):
        werte = [a.punkte_erreicht for a in self.aufgaben if a.punkte_erreicht is not None]
        return sum(werte) if werte else None

    @property
    def letzte_abgabe(self):
        return self.abgaben[-1] if self.abgaben else None


# Kompetenzniveau einer korrigierten Aufgabe. 1–3 werden aus den Punkten vorgeschlagen, 4 nur von Hand.
NIVEAUS = {1: "Gestartet", 2: "Solide Basis", 3: "Fortgeschritten", 4: "Instruktor"}
NIVEAU_BESCHREIBUNG = {1: "gerade begonnen, noch viele Korrekturen", 2: "solide Basis, wenige Fehler",
                       3: "fortgeschritten, fast fehlerfrei", 4: "kann es anderen erklären"}
NIVEAU_SCHWELLEN = (0.5, 0.8)  # Anteil der Punkte: < 50 % → 1, < 80 % → 2, sonst 3


def niveau_aus_punkten(erreicht, maximum):
    if erreicht is None or not maximum:
        return None
    anteil = erreicht / maximum
    return 1 if anteil < NIVEAU_SCHWELLEN[0] else 2 if anteil < NIVEAU_SCHWELLEN[1] else 3


class BlattAufgabe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    blatt_id = db.Column(db.Integer, db.ForeignKey("uebungsblatt.id"), nullable=False)
    blatt = db.relationship("Uebungsblatt", back_populates="aufgaben")
    aufgabe_id = db.Column(db.Integer, db.ForeignKey("aufgabe.id"), nullable=False)
    aufgabe = db.relationship("Aufgabe")
    position = db.Column(db.Integer, nullable=False)
    seed = db.Column(db.Integer)  # Zufallszahlen/Reihenfolge dieser Aufgabe auf diesem Blatt
    punkte_erreicht = db.Column(db.Float)
    kommentar = db.Column(db.Text, default="")
    niveau = db.Column(db.Integer)  # siehe NIVEAUS


class Abgabe(db.Model):
    """Eine Einreichung (Fotos/Scan) zu einem Übungsblatt."""
    id = db.Column(db.Integer, primary_key=True)
    blatt_id = db.Column(db.Integer, db.ForeignKey("uebungsblatt.id"), nullable=False)
    blatt = db.relationship("Uebungsblatt", back_populates="abgaben")
    hochgeladen_am = db.Column(db.DateTime, default=now)
    seiten = db.relationship("AbgabeSeite", order_by="AbgabeSeite.nr", cascade="all, delete-orphan",
                             back_populates="abgabe")


class AbgabeSeite(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    abgabe_id = db.Column(db.Integer, db.ForeignKey("abgabe.id"), nullable=False)
    abgabe = db.relationship("Abgabe", back_populates="seiten")
    nr = db.Column(db.Integer, nullable=False)
    bild = db.Column(db.String(255), nullable=False)            # Originalfoto (normalisiert)
    annotationen = db.Column(db.Text)                           # JSON (Vektordaten, wieder editierbar)
    bild_korrigiert = db.Column(db.String(255))                 # Foto mit eingebrannten Korrekturen


# ---------------------------------------------------------------- Prüfungen

class Pruefung(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titel = db.Column(db.String(200), nullable=False)
    lp_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    lp = db.relationship("User")
    # Klasse ↔ Lehrperson verweisen gegenseitig aufeinander: benannte, nachträglich angelegte Fremdschlüssel,
    # damit PostgreSQL die Tabellen in beliebiger Reihenfolge anlegen und löschen kann
    klasse_id = db.Column(db.Integer, db.ForeignKey("klasse.id", use_alter=True, name="fk_user_klasse"))
    klasse = db.relationship("Klasse")
    datum = db.Column(db.String(40), default="")
    dauer_min = db.Column(db.Integer)
    hinweise = db.Column(db.Text, default="")
    parameter = db.Column(db.Text, default="{}")  # JSON der Generator-Parameter
    erstellt_am = db.Column(db.DateTime, default=now)
    aufgaben = db.relationship("PruefungAufgabe", order_by="PruefungAufgabe.position",
                               cascade="all, delete-orphan", back_populates="pruefung")

    @property
    def max_punkte(self):
        return sum(a.aufgabe.punkte for a in self.aufgaben)


class PruefungAufgabe(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    pruefung_id = db.Column(db.Integer, db.ForeignKey("pruefung.id"), nullable=False)
    pruefung = db.relationship("Pruefung", back_populates="aufgaben")
    aufgabe_id = db.Column(db.Integer, db.ForeignKey("aufgabe.id"), nullable=False)
    aufgabe = db.relationship("Aufgabe")
    position = db.Column(db.Integer, nullable=False)
    seed = db.Column(db.Integer)


# ---------------------------------------------------------------- Review

REVIEW_STELLEN = {"text": "Aufgabentext", "loesung": "Musterlösung", "bild": "Grafik", "zuordnung": "Themen/Lernziele",
                  "punkte": "Punkte/Niveau", "sonstiges": "Sonstiges"}
REVIEW_STATUS = {"offen": "offen", "vorschlag": "Vorschlag bereit", "rueckfrage": "Rückfrage",
                 "erledigt": "erledigt", "abgelehnt": "abgelehnt"}


class ReviewKommentar(db.Model):
    """Hinweis eines Reviewers zu einer Aufgabe oder einem Theoriekapitel.

    Ablauf: offen → (Claude Code über die Agent-Schnittstelle) vorschlag | rueckfrage → erledigt | abgelehnt.
    Eine beantwortete Rückfrage setzt den Status wieder auf offen. Änderungen übernimmt nur die Lehrperson.
    """
    id = db.Column(db.Integer, primary_key=True)
    autor_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    autor = db.relationship("User")
    aufgabe_id = db.Column(db.Integer, db.ForeignKey("aufgabe.id"))
    aufgabe = db.relationship("Aufgabe", backref=db.backref("review_kommentare", order_by="ReviewKommentar.id"))
    kapitel_id = db.Column(db.Integer, db.ForeignKey("theorie_kapitel.id"))
    kapitel = db.relationship("TheorieKapitel", back_populates="review_kommentare")
    stelle = db.Column(db.String(20), default="sonstiges")
    zitat = db.Column(db.Text, default="")
    text = db.Column(db.Text, nullable=False)
    status = db.Column(db.String(20), default="offen", nullable=False, index=True)
    zusammenfassung = db.Column(db.Text, default="")   # Einschätzung von Claude
    vorschlag = db.Column(db.Text)                     # JSON: geänderte Felder ({} = keine Änderung nötig)
    verlauf = db.Column(db.Text, default="[]")         # JSON: [{wer, art, text, zeit}]
    erstellt_am = db.Column(db.DateTime, default=now)
    geaendert_am = db.Column(db.DateTime, default=now, onupdate=now)

    @property
    def ziel_label(self):
        if self.aufgabe:
            return f"Aufgabe #{self.aufgabe.id}: {self.aufgabe.titel}"
        if self.kapitel:
            return f"Theorie {self.kapitel.label}"
        return "(gelöscht)"

    @property
    def eintraege(self):
        return json.loads(self.verlauf or "[]")

    def eintrag(self, wer, art, text):
        self.verlauf = json.dumps(self.eintraege + [{"wer": wer, "art": art, "text": text,
                                                     "zeit": now().strftime("%d.%m.%Y %H:%M")}], ensure_ascii=False)

    @property
    def vorschlag_dict(self):
        return json.loads(self.vorschlag) if self.vorschlag else None


class LoginVersuch(db.Model):
    """Anmeldeversuche für die Sperre bei wiederholten Fehlversuchen (werden nach einem Tag gelöscht)."""
    id = db.Column(db.Integer, primary_key=True)
    zeit = db.Column(db.DateTime, default=now, index=True)
    benutzername = db.Column(db.String(80), index=True)
    ip = db.Column(db.String(64), index=True)
    erfolgreich = db.Column(db.Boolean, default=False, nullable=False)


class KiProtokoll(db.Model):
    """Verbrauch des KI-Assistenten (für Transparenz und Kostenkontrolle). Enthält keine Inhalte."""
    id = db.Column(db.Integer, primary_key=True)
    zeit = db.Column(db.DateTime, default=now, index=True)
    lp_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    lp = db.relationship("User")
    aktion = db.Column(db.String(20), nullable=False)
    modell = db.Column(db.String(60))
    input_tokens = db.Column(db.Integer, default=0)
    output_tokens = db.Column(db.Integer, default=0)
    cache_lesen = db.Column(db.Integer, default=0)
    cache_schreiben = db.Column(db.Integer, default=0)


class Einstellung(db.Model):
    """Einstellung der Installation (Schlüssel/Wert), siehe app/einstellungen.py."""
    schluessel = db.Column(db.String(40), primary_key=True)
    wert = db.Column(db.Text, nullable=False, default="")


SPALTEN_NACHTRAG = [  # (Tabelle, Spalte, DDL) – für bestehende Datenbanken ohne Migrationswerkzeug
    ("aufgabe", "typ", "VARCHAR(12) NOT NULL DEFAULT 'frei'"),
    ("aufgabe", "daten", "TEXT NOT NULL DEFAULT '{}'"),
    ("blatt_aufgabe", "seed", "INTEGER"),
    ("pruefung_aufgabe", "seed", "INTEGER"),
    ("user", "passwort_aendern", "BOOLEAN NOT NULL DEFAULT FALSE"),
    ("blatt_aufgabe", "niveau", "INTEGER"),
    ("user", "ist_admin", "BOOLEAN NOT NULL DEFAULT FALSE"),
]


def spalten_ergaenzen():
    """Fügt neue Spalten in bestehende Tabellen ein (db.create_all() ergänzt nur fehlende Tabellen)."""
    insp = db.inspect(db.engine)
    for tabelle, spalte, ddl in SPALTEN_NACHTRAG:
        if tabelle in insp.get_table_names() and spalte not in {c["name"] for c in insp.get_columns(tabelle)}:
            q = db.engine.dialect.identifier_preparer.quote  # «user» ist in PostgreSQL reserviert
            db.session.execute(db.text(f"ALTER TABLE {q(tabelle)} ADD COLUMN {q(spalte)} {ddl}"))
    db.session.commit()

#!/usr/bin/env python3
"""
U nengue — Na buranghe ô dji icole di Gabu
École primaire gabonaise - 1ère à 5ème année
Système APC (Approche Par Compétences)
"""

from flask import (Flask, render_template, request, redirect, url_for,
                   flash, session, send_file, send_from_directory)
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from datetime import datetime, date, timedelta
from functools import wraps
from collections import defaultdict
import os
import io
import base64

app = Flask(__name__)
# Sécurité : clé secrète depuis variable d'environnement en production
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'u-nengue-changez-moi-en-production-2026')
_BASE_DIR = os.path.abspath(os.path.dirname(__file__))
_DB_PATH = os.path.join(_BASE_DIR, 'kyaf_edu.db')
app.config['SQLALCHEMY_DATABASE_URI'] = os.environ.get('DATABASE_URL', 'sqlite:///' + _DB_PATH)
if app.config['SQLALCHEMY_DATABASE_URI'].startswith('postgres://'):
    app.config['SQLALCHEMY_DATABASE_URI'] = app.config['SQLALCHEMY_DATABASE_URI'].replace('postgres://', 'postgresql://', 1)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
app.config['PERMANENT_SESSION_LIFETIME'] = 28800  # 8 heures

db = SQLAlchemy(app)

ALLOWED_EXT = {'png', 'jpg', 'jpeg', 'gif', 'pdf', 'webp'}

# ==================== COMPETENCES APC GABON ====================
COMPETENCES = {
    'EDM&EAS': {
        'label': 'Étude du Milieu et Éducation Artistique et Sportive',
        'comps': {
            'C1': 'Histoire, Géographie, Éducation à la citoyenneté',
            'C2': 'Biologie, Sciences physiques, Technologie, TIC',
            'C3': 'Éducation artistique, Éducation physique et sportive',
        }
    },
    'FRANCAIS': {
        'label': 'Français',
        'comps': {
            'C1': 'Production orale',
            'C2': 'Lecture, Outils de la langue, Production écrite',
        }
    },
    'MATHS': {
        'label': 'Mathématiques',
        'comps': {
            'C1': 'Nombres et opérations, Résolution de problèmes',
            'C2': 'Géométrie, Mesure',
        }
    }
}

NIVEAUX = ['1ère année', '2ème année', '3ème année', '4ème année', '5ème année']
PALIERS = ['Palier 1', 'Palier 2', 'Palier 3', 'Palier 4', 'Palier 5']

def mastery_from_score(score):
    """Maîtrise de la compétence selon la note de compétence (somme des critères 0-4).
    Maxi: 8 à 12 | Mini: 5 à 7 | Part: 3 à 4 | NM: 0 à 2
    """
    if score is None:
        return None
    try:
        score = float(score)
    except (TypeError, ValueError):
        return None
    if score >= 8:
        return 'Maxi'
    if score >= 5:
        return 'Mini'
    if score >= 3:
        return 'Part'
    return 'NM'

def mastery_class(m):
    return {
        'Maxi': 'badge-maxi',
        'Mini': 'badge-mini',
        'Part': 'badge-part',
        'NM': 'badge-nm'
    }.get(m, 'badge-secondary')

# ==================== MODELS ====================

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    full_name = db.Column(db.String(120))
    email = db.Column(db.String(120), default='')
    role = db.Column(db.String(50), default='Directeur')  # Directeur / Enseignant
    class_id = db.Column(db.Integer, db.ForeignKey('class_room.id'), nullable=True)
    reset_code = db.Column(db.String(20), default='')
    classroom = db.relationship('ClassRoom', foreign_keys=[class_id])

class SchoolSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    school_name = db.Column(db.String(200), default='École Primaire')
    address = db.Column(db.String(300), default='')
    phone = db.Column(db.String(50), default='')
    email = db.Column(db.String(120), default='')
    province = db.Column(db.String(100), default='')
    circonscription = db.Column(db.String(100), default='')
    director_name = db.Column(db.String(120), default='')
    annee_scolaire = db.Column(db.String(20), default='2025-2026')
    # SMS (Twilio ou compatible)
    sms_enabled = db.Column(db.Boolean, default=False)
    sms_provider = db.Column(db.String(50), default='twilio')  # twilio / manuel
    sms_account_sid = db.Column(db.String(120), default='')
    sms_auth_token = db.Column(db.String(120), default='')
    sms_from_number = db.Column(db.String(30), default='')

class ClassRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(80), nullable=False)
    level = db.Column(db.String(30))  # 1ère année ... 5ème année
    teacher = db.Column(db.String(120))
    students = db.relationship('Student', backref='classroom', lazy=True)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    matricule = db.Column(db.String(50), unique=True)
    last_name = db.Column(db.String(80), nullable=False)
    first_name = db.Column(db.String(80), nullable=False)
    birth_date = db.Column(db.Date)
    birth_place = db.Column(db.String(150))  # Lieu de naissance
    gender = db.Column(db.String(10))
    class_id = db.Column(db.Integer, db.ForeignKey('class_room.id'))
    parent_name = db.Column(db.String(120))
    parent_phone = db.Column(db.String(50))
    parent_relation = db.Column(db.String(30), default='Père')
    address = db.Column(db.String(200))
    photo_path = db.Column(db.String(300))
    status = db.Column(db.String(20), default='Nouveau')  # Nouveau / Redoublant
    nationality = db.Column(db.String(50), default='Gabonaise')
    provenance = db.Column(db.String(50), default='meme_ecole')
    # meme_ecole | meme_circonscription | autres_circonscriptions | autres
    is_handicapped = db.Column(db.Boolean, default=False)
    is_primal = db.Column(db.Boolean, default=False)  # Primaux arrivés
    cep_selected = db.Column(db.Boolean, default=False)
    cep_admis = db.Column(db.Boolean, default=False)
    annee_inscription = db.Column(db.String(20), default='2025-2026')
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def full_name(self):
        return f"{self.last_name} {self.first_name}"

class StudentDocument(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    doc_type = db.Column(db.String(80))  # Acte de naissance, Certificat médical...
    filename = db.Column(db.String(300))
    original_name = db.Column(db.String(200))
    uploaded_at = db.Column(db.DateTime, default=datetime.utcnow)
    student = db.relationship('Student', backref='documents')

class Evaluation(db.Model):
    """Note par critère pour une compétence d'un palier"""
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    palier = db.Column(db.String(20), default='Palier 1')
    matiere = db.Column(db.String(30))  # EDM&EAS, FRANCAIS, MATHS
    competence = db.Column(db.String(5))  # C1, C2, C3
    critere = db.Column(db.String(5))  # c1, c2, c3 (note du critère)
    score = db.Column(db.Float)  # 0 à 9
    student = db.relationship('Student', backref='evaluations')

class Message(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    from_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    to_user_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    subject = db.Column(db.String(200), default='')
    body = db.Column(db.Text, nullable=False)
    is_read = db.Column(db.Boolean, default=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    sender = db.relationship('User', foreign_keys=[from_user_id])
    recipient = db.relationship('User', foreign_keys=[to_user_id])

class SmsLog(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=True)
    phone = db.Column(db.String(30))
    recipient_name = db.Column(db.String(120))
    body = db.Column(db.Text)
    status = db.Column(db.String(30), default='pending')  # sent / failed / pending / manual
    error_message = db.Column(db.String(300), default='')
    sent_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    student = db.relationship('Student', backref='sms_logs')

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('student.id'), nullable=False)
    date = db.Column(db.Date, default=date.today)
    status = db.Column(db.String(30), default='Présent')  # Présent, Absent, Retard, Excusé
    student = db.relationship('Student', backref='attendances')

class Publication(db.Model):
    """Actualités publiées par le directeur"""
    id = db.Column(db.Integer, primary_key=True)
    title = db.Column(db.String(200), nullable=False)
    kind = db.Column(db.String(30), default='article')  # article, photo, document, video
    body = db.Column(db.Text, default='')
    filename = db.Column(db.String(300), default='')
    original_name = db.Column(db.String(200), default='')
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author = db.relationship('User')

class Textbook(db.Model):
    """Manuels scolaires en usage"""
    id = db.Column(db.Integer, primary_key=True)
    discipline = db.Column(db.String(80), nullable=False)
    title = db.Column(db.String(250), nullable=False)
    editor = db.Column(db.String(120), default='IPN')
    level = db.Column(db.String(40), default='')  # optionnel: 5ème année...

class Holiday(db.Model):


    """Jours fériés / non ouvrés (école fermée)"""
    id = db.Column(db.Integer, primary_key=True)
    date = db.Column(db.Date, nullable=False, unique=True)
    label = db.Column(db.String(120), default='Jour férié')

class ClassJournal(db.Model):
    """Cahier journal par classe"""
    id = db.Column(db.Integer, primary_key=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class_room.id'), nullable=False)
    date = db.Column(db.Date, default=date.today)
    subject = db.Column(db.String(120), default='')
    content = db.Column(db.Text, default='')  # leçon / activités
    observation = db.Column(db.Text, default='')  # observations enseignant
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    classroom = db.relationship('ClassRoom', backref='journal_entries')
    author = db.relationship('User')

# ==================== HELPERS ====================

def allowed_file(filename):
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXT


def normalize_phone_wa(phone):
    """Normalise un numéro gabonais pour wa.me (indicatif 241)"""
    if not phone:
        return None
    digits = ''.join(c for c in phone if c.isdigit())
    if not digits:
        return None
    if digits.startswith('241'):
        return digits
    if digits.startswith('0'):
        digits = digits[1:]
    return '241' + digits

def whatsapp_link(phone, message=''):
    num = normalize_phone_wa(phone)
    if not num:
        return None
    from urllib.parse import quote
    return f'https://wa.me/{num}?text={quote(message)}'


def send_sms_api(to_phone, body, settings):
    """Envoie un SMS via Twilio si configuré. Retourne (ok: bool, detail: str)."""
    if not settings or not settings.sms_enabled:
        return False, 'SMS non activé dans les paramètres'
    if settings.sms_provider != 'twilio':
        return False, 'Mode manuel — utilisez le lien sms:'
    sid = (settings.sms_account_sid or '').strip()
    token = (settings.sms_auth_token or '').strip()
    from_num = (settings.sms_from_number or '').strip()
    if not sid or not token or not from_num:
        return False, 'Identifiants SMS incomplets'
    to_num = normalize_phone_wa(to_phone)
    if not to_num:
        return False, 'Numéro invalide'
    to_e164 = '+' + to_num
    try:
        import urllib.request
        import urllib.parse
        import base64
        data = urllib.parse.urlencode({
            'To': to_e164,
            'From': from_num,
            'Body': body
        }).encode('utf-8')
        req = urllib.request.Request(
            f'https://api.twilio.com/2010-04-01/Accounts/{sid}/Messages.json',
            data=data,
            method='POST'
        )
        credentials = base64.b64encode(f'{sid}:{token}'.encode()).decode()
        req.add_header('Authorization', f'Basic {credentials}')
        with urllib.request.urlopen(req, timeout=20) as resp:
            if 200 <= resp.status < 300:
                return True, 'Envoyé'
            return False, f'Erreur HTTP {resp.status}'
    except Exception as e:
        return False, str(e)[:250]



# Jours fériés fixes Gabon (mois, jour) — complétés par table Holiday
GABON_FIXED_HOLIDAYS = {
    (1, 1): 'Jour de l\'An',
    (3, 12): 'Fête de la Rénovation',
    (5, 1): 'Fête du Travail',
    (8, 15): 'Assomption',
    (8, 16): 'Indépendance du Gabon',
    (8, 17): 'Fête nationale',
    (11, 1): 'Toussaint',
    (12, 25): 'Noël',
}

def is_holiday(d):
    if not d:
        return False, None
    fixed = GABON_FIXED_HOLIDAYS.get((d.month, d.day))
    if fixed:
        return True, fixed
    h = Holiday.query.filter_by(date=d).first()
    if h:
        return True, h.label
    return False, None

def is_school_day(d):
    """Jour ouvrable scolaire : pas weekend, pas férié"""
    if d.weekday() >= 5:  # samedi=5 dimanche=6
        return False
    hol, _ = is_holiday(d)
    return not hol

def school_days_between(start, end):
    days = []
    cur = start
    while cur <= end:
        if is_school_day(cur):
            days.append(cur)
        cur += timedelta(days=1)
    return days

def attendance_stats(class_id, start, end):
    """% présence / absence pour une classe sur une période"""
    students = Student.query.filter_by(class_id=class_id).all()
    days = school_days_between(start, end)
    if not students or not days:
        return {'students': [], 'pct_presence': 0, 'pct_absence': 0, 'days': 0}
    total_expected = 0
    total_present = 0
    total_absent = 0
    rows = []
    for s in students:
        atts = Attendance.query.filter(
            Attendance.student_id == s.id,
            Attendance.date >= start,
            Attendance.date <= end
        ).all()
        by_date = {a.date: a.status for a in atts}
        present = absent = retard = 0
        for d in days:
            st = by_date.get(d)
            if st in ('Présent', 'Retard', 'Retard justifié', 'Retard injustifié'):
                present += 1
                if st and 'Retard' in st:
                    retard += 1
            elif st in ('Absent', 'Absence justifiée', 'Absence injustifiée', 'Excusé'):
                absent += 1
            # non marqué = non compté dans le %
        marked = present + absent
        total_expected += marked
        total_present += present
        total_absent += absent
        pct_p = round(100 * present / marked, 1) if marked else None
        rows.append({
            'student': s, 'present': present, 'absent': absent,
            'retard': retard, 'marked': marked, 'pct_presence': pct_p
        })
    pct_presence = round(100 * total_present / total_expected, 1) if total_expected else 0
    pct_absence = round(100 * total_absent / total_expected, 1) if total_expected else 0
    return {
        'students': rows, 'pct_presence': pct_presence, 'pct_absence': pct_absence,
        'days': len(days), 'total_present': total_present, 'total_absent': total_absent
    }



MOIS_SCOLAIRES = [
    (9, 'Septembre'), (10, 'Octobre'), (11, 'Novembre'), (12, 'Décembre'),
    (1, 'Janvier'), (2, 'Février'), (3, 'Mars'), (4, 'Avril'),
    (5, 'Mai'), (6, 'Juin'), (7, 'Juillet'),
]

def auto_observation(pct_present):
    if pct_present is None:
        return ''
    if pct_present >= 95:
        return 'Bonne fréquentation'
    if pct_present >= 90:
        return 'Fréquentation correcte'
    if pct_present >= 85:
        return 'Baisse à surveiller'
    if pct_present >= 75:
        return 'Courbe descendante'
    return 'Fréquentation insuffisante'


def compute_frequentation(class_id, year=None):
    """Tableau de fréquentation mensuel (année scolaire sept→juil)"""
    today = date.today()
    # Année scolaire : si mois >= 9, année = année civile ; sinon année civile - 1
    if year is None:
        year = today.year if today.month >= 9 else today.year - 1

    months = []
    total_present = total_absent = total_marked = 0

    for month_num, label in MOIS_SCOLAIRES:
        y = year if month_num >= 9 else year + 1
        # bornes du mois
        start = date(y, month_num, 1)
        if month_num == 12:
            end = date(y, 12, 31)
        else:
            end = date(y, month_num + 1, 1) - timedelta(days=1)
        # ne pas dépasser aujourd'hui
        if start > today:
            months.append({
                'month': month_num, 'label': label, 'year': y,
                'pct_present': None, 'pct_absent': None,
                'observation': '', 'present': 0, 'absent': 0, 'marked': 0,
                'future': True
            })
            continue
        end_eff = min(end, today)
        st = attendance_stats(class_id, start, end_eff)
        marked = st.get('total_present', 0) + st.get('total_absent', 0)
        present = st.get('total_present', 0)
        absent = st.get('total_absent', 0)
        total_present += present
        total_absent += absent
        total_marked += marked
        pct_p = st.get('pct_presence')
        pct_a = st.get('pct_absence')
        months.append({
            'month': month_num, 'label': label, 'year': y,
            'pct_present': pct_p, 'pct_absent': pct_a,
            'observation': auto_observation(pct_p) if marked else '',
            'present': present, 'absent': absent, 'marked': marked,
            'future': False
        })

    if total_marked:
        ann_p = round(100 * total_present / total_marked, 2)
        ann_a = round(100 * total_absent / total_marked, 2)
    else:
        ann_p = ann_a = None

    return {
        'year': year,
        'year_label': f'{year}-{year+1}',
        'months': months,
        'annuel': {
            'pct_present': ann_p,
            'pct_absent': ann_a,
            'observation': auto_observation(ann_p) if ann_p is not None else '',
            'present': total_present,
            'absent': total_absent,
            'marked': total_marked,
        }
    }


def sex_of(s):
    g = (s.gender or '').upper()
    if g in ('M', 'MASCULIN', 'GARCON', 'G'):
        return 'G'
    if g in ('F', 'FEMININ', 'FILLE'):
        return 'F'
    return '?'

def gft(students):
    g = sum(1 for s in students if sex_of(s) == 'G')
    f = sum(1 for s in students if sex_of(s) == 'F')
    return {'G': g, 'F': f, 'T': len(students)}

def compute_class_stats(class_id=None):
    """Statistiques officielles (classe ou école entière)"""
    q = Student.query
    if class_id:
        q = q.filter_by(class_id=class_id)
    students = q.all()
    today = date.today()
    school_year = today.year if today.month >= 9 else today.year - 1

    # Répartition inscrits
    nouveaux = [s for s in students if (s.status or '').lower() in ('nouveau', 'nouvelle', '')]
    redoublants = [s for s in students if (s.status or '').lower() in ('redoublant', 'redoublante')]
    primaux = [s for s in students if getattr(s, 'is_primal', False)]
    handicapes = [s for s in students if getattr(s, 'is_handicapped', False)]

    repartition = {
        'inscrits': gft(students),
        'nouveaux': gft(nouveaux),
        'redoublants': gft(redoublants),
        'primaux': gft(primaux),
        'handicapes': gft(handicapes),
    }

    # Nationalité
    gab = [s for s in students if not getattr(s, 'nationality', None) or 'gabon' in (getattr(s, 'nationality', '') or '').lower()]
    nongab = [s for s in students if getattr(s, 'nationality', None) and 'gabon' not in (getattr(s, 'nationality', '') or '').lower()]
    nationalite = {'gabonais': gft(gab), 'non_gabonais': gft(nongab)}

    # Mobilité géographique
    prov_map = {
        'meme_ecole': 'Même École',
        'meme_circonscription': 'Différentes Écoles Même circonscription',
        'autres_circonscriptions': 'Autres circonscriptions',
        'autres': 'Autres',
    }
    mobilite = {}
    for key, label in prov_map.items():
        mobilite[key] = {'label': label, **gft([s for s in students if (getattr(s, 'provenance', None) or 'meme_ecole') == key])}
    mobilite['total'] = {'label': 'Total', **gft(students)}

    # Âges (début d'année = 1er sept de l'année scolaire)
    ref_debut = date(school_year, 9, 1)
    age_rows = []
    for age in range(5, 17):
        birth_year = school_year - age
        group = [s for s in students if s.birth_date and s.birth_date.year == birth_year]
        # âge exact au 1er sept
        exact = []
        for s in students:
            if not s.birth_date:
                continue
            a = school_year - s.birth_date.year
            if s.birth_date.replace(year=school_year) > ref_debut:
                a -= 1
            if a == age:
                exact.append(s)
        # Prefer exact age; fallback birth year table style
        use = exact if exact else group
        age_rows.append({
            'age': age,
            'birth_year': birth_year,
            'label': f'{age:02d} ans' if age < 16 else ('16 ans' if age == 16 else '+ de 16 ans'),
            **gft(use),
        })
    # + de 16
    plus16 = [s for s in students if s.birth_date and (school_year - s.birth_date.year) >= 17]
    age_rows.append({'age': 17, 'birth_year': school_year - 17, 'label': '+ de 16 ans', **gft(plus16)})

    # Effectifs mensuels (basés sur date d'inscription created_at)
    effectifs_mensuels = []
    for month_num, label in MOIS_SCOLAIRES:
        y = school_year if month_num >= 9 else school_year + 1
        # élèves inscrits avant la fin du mois
        if month_num == 12:
            end = date(y, 12, 31)
        else:
            end = date(y, month_num + 1, 1) - timedelta(days=1)
        if date(y, month_num, 1) > today:
            effectifs_mensuels.append({'label': label, 'G': None, 'F': None, 'T': None, 'future': True})
            continue
        enrolled = [s for s in students if s.created_at and s.created_at.date() <= end]
        # Si pas de created_at fiable, prendre tous pour mois passés
        if not any(s.created_at for s in students):
            enrolled = students
        effectifs_mensuels.append({'label': label, **gft(enrolled), 'future': False})

    # Pyramide (même que age_rows mais format compact 7-16)
    pyramide = [r for r in age_rows if 7 <= r['age'] <= 16]
    max_pyr = max([r['T'] for r in pyramide], default=1) or 1

    return {
        'students': students,
        'school_year': school_year,
        'year_label': f'{school_year}-{school_year+1}',
        'repartition': repartition,
        'nationalite': nationalite,
        'mobilite': mobilite,
        'ages': age_rows,
        'effectifs_mensuels': effectifs_mensuels,
        'pyramide': pyramide,
        'max_pyramid': max_pyr,
        'textbooks': Textbook.query.order_by(Textbook.discipline, Textbook.title).all() if 'textbook' in inspect_tables() else [],
    }


def inspect_tables():
    try:
        from sqlalchemy import inspect
        return set(inspect(db.engine).get_table_names())
    except Exception:
        return set()

def migrate_schema():
    """Ajoute les colonnes manquantes sans casser la base existante"""
    from sqlalchemy import text as sa_text, inspect
    try:
        insp = inspect(db.engine)
        if 'student' in insp.get_table_names():
            cols = {c['name'] for c in insp.get_columns('student')}
            alters = []
            if 'nationality' not in cols:
                alters.append("ALTER TABLE student ADD COLUMN nationality VARCHAR(50) DEFAULT 'Gabonaise'")
            if 'provenance' not in cols:
                alters.append("ALTER TABLE student ADD COLUMN provenance VARCHAR(50) DEFAULT 'meme_ecole'")
            if 'is_handicapped' not in cols:
                alters.append("ALTER TABLE student ADD COLUMN is_handicapped BOOLEAN DEFAULT 0")
            if 'is_primal' not in cols:
                alters.append("ALTER TABLE student ADD COLUMN is_primal BOOLEAN DEFAULT 0")
            if 'email' not in cols and False:
                pass
            with db.engine.begin() as conn:
                for sql in alters:
                    try:
                        conn.execute(sa_text(sql))
                    except Exception:
                        pass
        # user email / reset_code
        if 'user' in insp.get_table_names():
            cols = {c['name'] for c in insp.get_columns('user')}
            with db.engine.begin() as conn:
                if 'email' not in cols:
                    try:
                        conn.execute(sa_text("ALTER TABLE user ADD COLUMN email VARCHAR(120) DEFAULT ''"))
                    except Exception:
                        pass
                if 'reset_code' not in cols:
                    try:
                        conn.execute(sa_text("ALTER TABLE user ADD COLUMN reset_code VARCHAR(20) DEFAULT ''"))
                    except Exception:
                        pass
    except Exception as e:
        print('migrate_schema:', e)

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Veuillez vous connecter.', 'warning')
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def director_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Veuillez vous connecter.', 'warning')
            return redirect(url_for('login'))
        if session.get('role') != 'Directeur':
            flash('Accès réservé au directeur.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

def teacher_class_filter():
    """Retourne class_id si enseignant, None si directeur (voit tout)"""
    if session.get('role') == 'Enseignant':
        return session.get('class_id')
    return None

_schema_ready = False

@app.before_request
def before_request_migrate():
    global _schema_ready
    if not _schema_ready:
        try:
            os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'photos'), exist_ok=True)
            os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'docs'), exist_ok=True)
            os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'publications'), exist_ok=True)
            db.create_all()
            migrate_schema()
            if not User.query.filter_by(username='admin').first():
                db.session.add(User(
                    username='admin',
                    password_hash=generate_password_hash('admin123'),
                    full_name='Directeur(trice)',
                    role='Directeur'
                ))
                db.session.commit()
            if not SchoolSettings.query.first():
                db.session.add(SchoolSettings(
                    school_name='École Publique Primaire',
                    annee_scolaire='2025-2026'
                ))
                db.session.commit()
        except Exception as e:
            print('auto-migrate:', e)
            try:
                db.session.rollback()
            except Exception:
                pass
        _schema_ready = True

@app.context_processor
def inject_globals():
    try:
        settings = SchoolSettings.query.first()
        students_count = Student.query.count()
    except Exception:
        settings = None
        students_count = 0
    return dict(settings=settings, students_count=students_count,
                mastery_class=mastery_class, COMPETENCES=COMPETENCES,
                NIVEAUX=NIVEAUX, PALIERS=PALIERS,
                theme=session.get('theme', 'fuchsia'))

@app.errorhandler(500)
def internal_error(e):
    import traceback
    traceback.print_exc()
    try:
        return render_template('login.html'), 500
    except Exception:
        return '<h1>Erreur serveur</h1><p>Rechargez dans 30 secondes. Si le problème continue, contactez le support.</p>', 500

# ==================== AUTH ====================

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        role_choice = request.form.get('role_choice', '')
        user = User.query.filter_by(username=username).first()
        if user and check_password_hash(user.password_hash, password):
            if role_choice and user.role != role_choice:
                flash(f'Ce compte est un compte « {user.role} ». Veuillez choisir le bon profil.', 'danger')
                return render_template('login.html')
            session['user_id'] = user.id
            session['username'] = user.username
            session['full_name'] = user.full_name
            session['role'] = user.role
            session['class_id'] = user.class_id
            flash(f'Bienvenue {user.full_name} ({user.role}) !', 'success')
            return redirect(url_for('dashboard'))
        flash('Identifiant ou mot de passe incorrect.', 'danger')
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash('Déconnexion réussie.', 'info')
    return redirect(url_for('login'))

# ==================== DASHBOARD ====================

@app.route('/')
@login_required
def dashboard():
    settings = SchoolSettings.query.first()
    total = Student.query.count()
    classes = ClassRoom.query.count()
    cep_count = Student.query.filter_by(cep_selected=True).count()
    by_level = []
    for n in NIVEAUX:
        c = Student.query.join(ClassRoom).filter(ClassRoom.level == n).count()
        by_level.append((n, c))
    recent = Student.query.order_by(Student.created_at.desc()).limit(5).all()
    try:
        news = Publication.query.order_by(Publication.created_at.desc()).limit(6).all()
    except Exception:
        news = []
    all_s = Student.query.all()
    gender_counts = gft(all_s) if all_s else {'G': 0, 'F': 0, 'T': 0}
    max_level = max([c for _, c in by_level], default=1) or 1
    return render_template('dashboard.html', total=total, classes=classes,
                           cep_count=cep_count, by_level=by_level, recent=recent,
                           news=news, gender_counts=gender_counts, max_level=max_level)

# ==================== ÉLÈVES ====================

@app.route('/eleves')
@login_required
def eleves():
    q = request.args.get('q', '')
    class_filter = request.args.get('class_id', '')
    level_filter = request.args.get('level', '')
    query = Student.query
    # Enseignant : uniquement sa classe
    tc = teacher_class_filter()
    if tc:
        query = query.filter_by(class_id=tc)
        class_filter = str(tc)
    if q:
        query = query.filter(
            db.or_(Student.last_name.ilike(f'%{q}%'),
                   Student.first_name.ilike(f'%{q}%'),
                   Student.matricule.ilike(f'%{q}%'))
        )
    if class_filter and not tc:
        query = query.filter_by(class_id=int(class_filter))
    if level_filter and not tc:
        query = query.join(ClassRoom).filter(ClassRoom.level == level_filter)
    students = query.order_by(Student.last_name).all()
    if tc:
        classes = ClassRoom.query.filter_by(id=tc).all()
    else:
        classes = ClassRoom.query.order_by(ClassRoom.level, ClassRoom.name).all()
    return render_template('eleves.html', students=students, classes=classes,
                           q=q, class_filter=class_filter, level_filter=level_filter)

@app.route('/eleves/ajouter', methods=['GET', 'POST'])
@director_required
def ajouter_eleve():
    classes = ClassRoom.query.order_by(ClassRoom.level).all()
    if request.method == 'POST':
        student = Student(
            matricule=request.form.get('matricule') or f"EPG-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            first_name=request.form.get('first_name'),
            last_name=request.form.get('last_name'),
            birth_date=datetime.strptime(request.form.get('birth_date'), '%Y-%m-%d').date() if request.form.get('birth_date') else None,
            birth_place=request.form.get('birth_place'),
            gender=request.form.get('gender'),
            nationality=request.form.get('nationality') or 'Gabonaise',
            provenance=request.form.get('provenance') or 'meme_ecole',
            is_handicapped=bool(request.form.get('is_handicapped')),
            is_primal=bool(request.form.get('is_primal')),
            class_id=int(request.form.get('class_id')) if request.form.get('class_id') else None,
            parent_name=request.form.get('parent_name'),
            parent_phone=request.form.get('parent_phone'),
            parent_relation=request.form.get('parent_relation', 'Père'),
            address=request.form.get('address'),
            status=request.form.get('status', 'Nouveau')
        )
        # Photo upload
        photo = request.files.get('photo')
        if photo and photo.filename and allowed_file(photo.filename):
            fname = secure_filename(f"{student.matricule}_{photo.filename}")
            path = os.path.join(app.config['UPLOAD_FOLDER'], 'photos', fname)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            photo.save(path)
            student.photo_path = f"uploads/photos/{fname}"
        # Webcam base64
        webcam_data = request.form.get('webcam_data')
        if webcam_data and webcam_data.startswith('data:image'):
            header, encoded = webcam_data.split(',', 1)
            data = base64.b64decode(encoded)
            fname = f"{student.matricule}_webcam.jpg"
            path = os.path.join(app.config['UPLOAD_FOLDER'], 'photos', fname)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                f.write(data)
            student.photo_path = f"uploads/photos/{fname}"
        db.session.add(student)
        db.session.commit()
        # Documents
        for key in request.files:
            if key.startswith('doc_'):
                f = request.files[key]
                if f and f.filename and allowed_file(f.filename):
                    dtype = key.replace('doc_', '').replace('_', ' ')
                    fname = secure_filename(f"{student.id}_{f.filename}")
                    path = os.path.join(app.config['UPLOAD_FOLDER'], 'docs', fname)
                    os.makedirs(os.path.dirname(path), exist_ok=True)
                    f.save(path)
                    db.session.add(StudentDocument(
                        student_id=student.id, doc_type=dtype,
                        filename=f"uploads/docs/{fname}", original_name=f.filename
                    ))
        db.session.commit()
        flash(f'Élève {student.full_name} inscrit avec succès.', 'success')
        return redirect(url_for('eleves'))
    return render_template('eleve_form.html', classes=classes, student=None)

@app.route('/eleves/<int:id>/modifier', methods=['GET', 'POST'])
@director_required
def modifier_eleve(id):
    student = Student.query.get_or_404(id)
    classes = ClassRoom.query.order_by(ClassRoom.level).all()
    if request.method == 'POST':
        student.first_name = request.form.get('first_name')
        student.last_name = request.form.get('last_name')
        student.matricule = request.form.get('matricule')
        if request.form.get('birth_date'):
            student.birth_date = datetime.strptime(request.form.get('birth_date'), '%Y-%m-%d').date()
        student.birth_place = request.form.get('birth_place')
        student.gender = request.form.get('gender')
        student.nationality = request.form.get('nationality') or 'Gabonaise'
        student.provenance = request.form.get('provenance') or 'meme_ecole'
        student.is_handicapped = bool(request.form.get('is_handicapped'))
        student.is_primal = bool(request.form.get('is_primal'))
        student.class_id = int(request.form.get('class_id')) if request.form.get('class_id') else None
        student.parent_name = request.form.get('parent_name')
        student.parent_phone = request.form.get('parent_phone')
        student.parent_relation = request.form.get('parent_relation')
        student.address = request.form.get('address')
        student.status = request.form.get('status', 'Nouveau')
        photo = request.files.get('photo')
        if photo and photo.filename and allowed_file(photo.filename):
            fname = secure_filename(f"{student.matricule}_{photo.filename}")
            path = os.path.join(app.config['UPLOAD_FOLDER'], 'photos', fname)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            photo.save(path)
            student.photo_path = f"uploads/photos/{fname}"
        webcam_data = request.form.get('webcam_data')
        if webcam_data and webcam_data.startswith('data:image'):
            header, encoded = webcam_data.split(',', 1)
            data = base64.b64decode(encoded)
            fname = f"{student.matricule}_webcam.jpg"
            path = os.path.join(app.config['UPLOAD_FOLDER'], 'photos', fname)
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, 'wb') as f:
                f.write(data)
            student.photo_path = f"uploads/photos/{fname}"
        db.session.commit()
        flash('Élève mis à jour.', 'success')
        return redirect(url_for('fiche_eleve', id=student.id))
    return render_template('eleve_form.html', classes=classes, student=student)

@app.route('/eleves/<int:id>')
@login_required
def fiche_eleve(id):
    student = Student.query.get_or_404(id)
    tc = teacher_class_filter()
    if tc and student.class_id != tc:
        flash('Accès réservé aux élèves de votre classe.', 'danger')
        return redirect(url_for('eleves'))
    return render_template('fiche_eleve.html', student=student)

@app.route('/eleves/<int:id>/fiche-pdf')
@login_required
def fiche_pdf(id):
    """Fiche d'inscription / renseignement en PDF"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    student = Student.query.get_or_404(id)
    tc = teacher_class_filter()
    if tc and student.class_id != tc:
        flash('Accès réservé aux élèves de votre classe.', 'danger')
        return redirect(url_for('eleves'))
    settings = SchoolSettings.query.first()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.2*cm, bottomMargin=1.2*cm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('t', parent=styles['Normal'], fontSize=14, alignment=TA_CENTER,
                           fontName='Helvetica-Bold', textColor=colors.HexColor('#a21caf'), spaceAfter=6)
    sub = ParagraphStyle('s', parent=styles['Normal'], fontSize=9, alignment=TA_CENTER, spaceAfter=10)
    label = ParagraphStyle('l', parent=styles['Normal'], fontSize=9, leading=12)
    elements = []

    elements.append(Paragraph("U nengue — Na buranghe ô dji icole di Gabu", sub))
    elements.append(Paragraph("FICHE D'INSCRIPTION / RENSEIGNEMENT", title))
    elements.append(Paragraph(
        f"{settings.school_name if settings else 'École Primaire'} — Année {settings.annee_scolaire if settings else ''}",
        sub))

    photo = ''
    if student.photo_path:
        ppath = os.path.join(os.path.dirname(__file__), 'static', student.photo_path)
        if os.path.exists(ppath):
            try:
                photo = Image(ppath, width=3*cm, height=3.5*cm)
            except Exception:
                photo = ''

    info_txt = f"""
<b>Nom :</b> {student.last_name}<br/>
<b>Prénom :</b> {student.first_name}<br/>
<b>Matricule :</b> {student.matricule or '—'}<br/>
<b>Date de naissance :</b> {student.birth_date.strftime('%d/%m/%Y') if student.birth_date else '—'}<br/>
<b>Lieu de naissance :</b> {student.birth_place or '—'}<br/>
<b>Sexe :</b> {'Masculin' if student.gender == 'M' else ('Féminin' if student.gender == 'F' else '—')}<br/>
<b>Classe :</b> {student.classroom.name if student.classroom else '—'} ({student.classroom.level if student.classroom else ''})<br/>
<b>Statut :</b> {student.status}<br/>
"""
    top = Table([[Paragraph(info_txt, label), photo if photo else Paragraph('', label)]],
                colWidths=[12*cm, 4*cm])
    top.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#c026d3')),
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fdf4ff')),
        ('LEFTPADDING', (0, 0), (-1, -1), 10),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(top)
    elements.append(Spacer(1, 8*mm))

    parent_txt = f"""
<b>PARENT / TUTEUR</b><br/><br/>
<b>Lien :</b> {student.parent_relation or '—'}<br/>
<b>Nom :</b> {student.parent_name or '—'}<br/>
<b>Téléphone :</b> {student.parent_phone or '—'}<br/>
<b>Adresse :</b> {student.address or '—'}
"""
    elements.append(Paragraph(parent_txt, label))
    elements.append(Spacer(1, 10*mm))

    if student.documents:
        docs = "<b>DOCUMENTS FOURNIS</b><br/>" + "<br/>".join(
            f"• {d.doc_type} ({d.original_name})" for d in student.documents
        )
        elements.append(Paragraph(docs, label))
        elements.append(Spacer(1, 10*mm))

    sig = Table([
        [Paragraph('<b>Signature du parent / tuteur</b><br/><br/><br/>________________', label),
         Paragraph("<b>Visa de l'administration</b><br/><br/><br/>________________", label)]
    ], colWidths=[8*cm, 8*cm])
    elements.append(sig)
    elements.append(Spacer(1, 8*mm))
    elements.append(Paragraph(
        f"Document genere par U nengue — {datetime.now().strftime('%d/%m/%Y %H:%M')}",
        ParagraphStyle('f', parent=styles['Normal'], fontSize=7, alignment=TA_CENTER, textColor=colors.grey)
    ))

    doc.build(elements)
    buffer.seek(0)
    fname = f"fiche_{student.last_name}_{student.first_name}.pdf".replace(' ', '_')
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=fname)


@app.route('/eleves/<int:id>/supprimer')
@director_required
def supprimer_eleve(id):
    student = Student.query.get_or_404(id)
    name = student.full_name
    Evaluation.query.filter_by(student_id=id).delete()
    Attendance.query.filter_by(student_id=id).delete()
    StudentDocument.query.filter_by(student_id=id).delete()
    db.session.delete(student)
    db.session.commit()
    flash(f'Élève {name} supprimé.', 'success')
    return redirect(url_for('eleves'))

@app.route('/eleves/supprimer-tous')
@director_required
def supprimer_tous_eleves():
    Evaluation.query.delete()
    Attendance.query.delete()
    StudentDocument.query.delete()
    n = Student.query.delete()
    db.session.commit()
    flash(f'Fichier nominatif effacé : {n} élève(s) supprimé(s).', 'success')
    return redirect(url_for('listes'))

# ==================== LISTES NOMINATIVES ====================

@app.route('/listes')
@login_required
def listes():
    tc = teacher_class_filter()
    if tc:
        classes = ClassRoom.query.filter_by(id=tc).all()
        all_students = Student.query.filter_by(class_id=tc).order_by(Student.last_name).all()
    else:
        classes = ClassRoom.query.order_by(ClassRoom.level, ClassRoom.name).all()
        all_students = Student.query.order_by(Student.last_name).all()
    return render_template('listes.html', classes=classes, all_students=all_students)

@app.route('/listes/classe/<int:id>')
@login_required
def liste_classe(id):
    room = ClassRoom.query.get_or_404(id)
    tc = teacher_class_filter()
    if tc and tc != id:
        flash('Accès réservé à votre classe uniquement.', 'danger')
        return redirect(url_for('listes'))
    students = Student.query.filter_by(class_id=id).order_by(Student.last_name).all()
    return render_template('liste_classe.html', room=room, students=students)

# ==================== CEP ====================

def cep_subject_averages(student_id):
    """Moyennes CEP : Français, Maths, Éveil (EDM&EAS) sur tous les paliers"""
    subjects = {'FRANCAIS': [], 'MATHS': [], 'EDM&EAS': []}
    for palier in ['Palier 1', 'Palier 2', 'Palier 3', 'Palier 4', 'Palier 5', 'Profil de sortie']:
        data, _ = compute_bulletin_data(student_id, palier)
        for key in subjects:
            comps = data.get(key, {}).get('comps', {})
            notes = [c.get('note') for c in comps.values() if c.get('note') is not None]
            if notes:
                subjects[key].append(sum(notes) / len(notes))
    result = {}
    for key, vals in subjects.items():
        result[key] = round(sum(vals) / len(vals), 2) if vals else None
    notes_ok = [v for v in result.values() if v is not None]
    result['moyenne'] = round(sum(notes_ok) / len(notes_ok), 2) if notes_ok else None
    return result

@app.route('/cep')
@director_required
def cep():
    students = Student.query.join(ClassRoom).filter(
        ClassRoom.level == '5ème année'
    ).order_by(Student.last_name).all()
    return render_template('cep.html', students=students)

@app.route('/cep/toggle/<int:id>')
@director_required
def cep_toggle(id):
    student = Student.query.get_or_404(id)
    student.cep_selected = not student.cep_selected
    db.session.commit()
    flash(f"{student.full_name} {'sélectionné' if student.cep_selected else 'retiré'} pour le CEP.", 'success')
    return redirect(url_for('cep'))

@app.route('/cep/candidats')
@director_required
def cep_candidats():
    """Liste nominative + relevé de notes des candidats CEP"""
    candidats = Student.query.filter_by(cep_selected=True).order_by(Student.last_name).all()
    rows = []
    for s in candidats:
        avg = cep_subject_averages(s.id)
        rows.append({
            'student': s,
            'francais': avg.get('FRANCAIS'),
            'maths': avg.get('MATHS'),
            'eveil': avg.get('EDM&EAS'),
            'moyenne': avg.get('moyenne'),
        })
    # Rang par moyenne décroissante
    ranked = sorted(rows, key=lambda r: (r['moyenne'] is not None, r['moyenne'] or 0), reverse=True)
    for i, r in enumerate(ranked, 1):
        r['rang'] = i if r['moyenne'] is not None else '—'
    settings = SchoolSettings.query.first()
    return render_template('cep_candidats.html', rows=ranked, settings=settings)

@app.route('/cep/candidats/pdf')
@director_required
def cep_candidats_pdf():
    """PDF liste + relevé candidats CEP"""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    candidats = Student.query.filter_by(cep_selected=True).order_by(Student.last_name).all()
    rows_data = []
    for s in candidats:
        avg = cep_subject_averages(s.id)
        rows_data.append({
            'student': s,
            'francais': avg.get('FRANCAIS'),
            'maths': avg.get('MATHS'),
            'eveil': avg.get('EDM&EAS'),
            'moyenne': avg.get('moyenne'),
        })
    ranked = sorted(rows_data, key=lambda r: (r['moyenne'] is not None, r['moyenne'] or 0), reverse=True)
    settings = SchoolSettings.query.first()
    annee = settings.annee_scolaire if settings else ''

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            leftMargin=1*cm, rightMargin=1*cm, topMargin=0.8*cm, bottomMargin=0.8*cm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('t', parent=styles['Normal'], fontSize=12, alignment=TA_CENTER,
                           fontName='Helvetica-Bold', spaceAfter=4)
    small = ParagraphStyle('s', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)
    cell = ParagraphStyle('c', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER)
    elements = []
    elements.append(Paragraph("U nengue — CANDIDATS AU CEP", title))
    elements.append(Paragraph(
        f"{settings.school_name if settings else ''} — Année {annee} — Liste nominative et relevé de notes",
        small))
    elements.append(Spacer(1, 4*mm))

    header = ['Rang', 'Nom et Prénom', 'Date de naissance', 'Lieu de naissance',
              'Français', 'Mathématiques', 'Éveil (EDM)', 'Moyenne']
    table_rows = [header]
    for i, r in enumerate(ranked, 1):
        s = r['student']
        table_rows.append([
            str(i) if r['moyenne'] is not None else '—',
            s.full_name,
            s.birth_date.strftime('%d/%m/%Y') if s.birth_date else '—',
            s.birth_place or '—',
            str(r['francais']) if r['francais'] is not None else '—',
            str(r['maths']) if r['maths'] is not None else '—',
            str(r['eveil']) if r['eveil'] is not None else '—',
            str(r['moyenne']) if r['moyenne'] is not None else '—',
        ])
    if len(table_rows) == 1:
        table_rows.append(['—', 'Aucun candidat sélectionné', '', '', '', '', '', ''])

    t = Table(table_rows, colWidths=[1.5*cm, 5.5*cm, 3.2*cm, 4*cm, 2.5*cm, 2.8*cm, 2.8*cm, 2.5*cm])
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c026d3')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#fdf4ff')]),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 6*mm))
    elements.append(Paragraph(
        "Éveil = EDM&EAS (Étude du Milieu et Éducation Artistique et Sportive). "
        "Moyenne = moyenne des trois disciplines. Rang calculé automatiquement.",
        ParagraphStyle('n', parent=styles['Normal'], fontSize=7, textColor=colors.grey)
    ))
    doc.build(elements)
    buffer.seek(0)
    safe_annee = (annee or 'annee').replace('-', '_').replace('/', '_')
    return send_file(buffer, mimetype='application/pdf', as_attachment=True,
                     download_name=f"candidats_CEP_{safe_annee}.pdf")


# ==================== CLASSES ====================

@app.route('/classes')
@director_required
def classes():
    rooms = ClassRoom.query.order_by(ClassRoom.level, ClassRoom.name).all()
    return render_template('classes.html', rooms=rooms)

@app.route('/classes/ajouter', methods=['GET', 'POST'])
@director_required
def ajouter_classe():
    if request.method == 'POST':
        room = ClassRoom(
            name=request.form.get('name'),
            level=request.form.get('level'),
            teacher=request.form.get('teacher')
        )
        db.session.add(room)
        db.session.commit()
        flash(f'Classe {room.name} créée.', 'success')
        return redirect(url_for('classes'))
    return render_template('classe_form.html', room=None)

@app.route('/classes/<int:id>/modifier', methods=['GET', 'POST'])
@director_required
def modifier_classe(id):
    room = ClassRoom.query.get_or_404(id)
    if request.method == 'POST':
        room.name = request.form.get('name')
        room.level = request.form.get('level')
        room.teacher = request.form.get('teacher')
        db.session.commit()
        flash('Classe mise à jour.', 'success')
        return redirect(url_for('classes'))
    return render_template('classe_form.html', room=room)

@app.route('/classes/<int:id>/supprimer')
@director_required
def supprimer_classe(id):
    room = ClassRoom.query.get_or_404(id)
    name = room.name
    # Supprimer tous les élèves de la classe d'abord
    for s in list(room.students):
        Evaluation.query.filter_by(student_id=s.id).delete()
        Attendance.query.filter_by(student_id=s.id).delete()
        StudentDocument.query.filter_by(student_id=s.id).delete()
        db.session.delete(s)
    db.session.delete(room)
    db.session.commit()
    flash(f'Classe {name} et ses élèves supprimés.', 'success')
    return redirect(url_for('classes'))

@app.route('/classes/<int:id>/vider')
@director_required
def vider_classe(id):
    room = ClassRoom.query.get_or_404(id)
    n = 0
    for s in list(room.students):
        Evaluation.query.filter_by(student_id=s.id).delete()
        Attendance.query.filter_by(student_id=s.id).delete()
        StudentDocument.query.filter_by(student_id=s.id).delete()
        db.session.delete(s)
        n += 1
    db.session.commit()
    flash(f'{n} élève(s) retiré(s) de la classe {room.name}.', 'success')
    return redirect(url_for('classes'))

# ==================== ÉVALUATIONS / NOTES ====================

@app.route('/evaluations')
@login_required
def evaluations():
    class_id = request.args.get('class_id')
    palier = request.args.get('palier', 'Palier 1')
    tc = teacher_class_filter()
    if tc:
        rooms = ClassRoom.query.filter_by(id=tc).all()
        selected = ClassRoom.query.get(tc)
    else:
        rooms = ClassRoom.query.order_by(ClassRoom.level).all()
        selected = ClassRoom.query.get(class_id) if class_id else (rooms[0] if rooms else None)
    students = Student.query.filter_by(class_id=selected.id).order_by(Student.last_name).all() if selected else []
    return render_template('evaluations.html', rooms=rooms, selected=selected,
                           students=students, palier=palier)

@app.route('/evaluations/saisir/<int:student_id>', methods=['GET', 'POST'])
@login_required
def saisir_evaluation(student_id):
    student = Student.query.get_or_404(student_id)
    palier = request.args.get('palier', request.form.get('palier', 'Palier 1'))
    if request.method == 'POST':
        # Delete existing for this palier
        Evaluation.query.filter_by(student_id=student_id, palier=palier).delete()
        for matiere, data in COMPETENCES.items():
            for comp in data['comps']:
                for crit in ['c1', 'c2', 'c3']:
                    key = f"{matiere}_{comp}_{crit}"
                    val = request.form.get(key)
                    if val is not None and val != '':
                        try:
                            score = float(val)
                            # Note du critère : entre 0 et 4
                            if score < 0:
                                score = 0
                            if score > 4:
                                score = 4
                            db.session.add(Evaluation(
                                student_id=student_id, palier=palier,
                                matiere=matiere, competence=comp,
                                critere=crit, score=score
                            ))
                        except ValueError:
                            pass
        db.session.commit()
        flash(f'Évaluation {palier} enregistrée pour {student.full_name}.', 'success')
        return redirect(url_for('bulletin', student_id=student_id, palier=palier))
    # Load existing
    existing = {}
    for e in Evaluation.query.filter_by(student_id=student_id, palier=palier).all():
        existing[f"{e.matiere}_{e.competence}_{e.critere}"] = e.score
    return render_template('saisir_evaluation.html', student=student,
                           palier=palier, existing=existing)

def compute_bulletin_data(student_id, palier):
    """Calcule notes de compétence, maîtrise, etc."""
    evals = Evaluation.query.filter_by(student_id=student_id, palier=palier).all()
    data = {}
    for matiere, minfo in COMPETENCES.items():
        data[matiere] = {'comps': {}, 'mastery_matiere': None}
        reussies = 0
        total_comps = len(minfo['comps'])
        for comp in minfo['comps']:
            # Notes de critères (chacune entre 0 et 4)
            crits = {}
            for crit in ['c1', 'c2', 'c3']:
                found = [e.score for e in evals if e.matiere == matiere and e.competence == comp and e.critere == crit]
                crits[crit] = found[0] if found else None
            # Note de la compétence = SOMME des notes de critères
            scores = [v for v in crits.values() if v is not None]
            if scores:
                note_comp = round(sum(scores), 1)
                mastery = mastery_from_score(note_comp)
                if mastery in ('Maxi', 'Mini'):
                    reussies += 1
            else:
                note_comp = None
                mastery = None
            data[matiere]['comps'][comp] = {
                'note': note_comp, 'mastery': mastery, 'crits': crits
            }
        # Maîtrise matière
        if total_comps == 3:
            if reussies == 3:
                data[matiere]['mastery_matiere'] = 'Maxi'
            elif reussies == 2:
                data[matiere]['mastery_matiere'] = 'Mini'
            elif reussies == 1:
                data[matiere]['mastery_matiere'] = 'Part'
            else:
                data[matiere]['mastery_matiere'] = 'NM' if any(
                    data[matiere]['comps'][c]['note'] is not None for c in minfo['comps']
                ) else None
        else:  # 2 comps
            if reussies == 2:
                data[matiere]['mastery_matiere'] = 'Maxi'
            elif reussies == 1:
                data[matiere]['mastery_matiere'] = 'Mini'
            else:
                data[matiere]['mastery_matiere'] = 'NM' if any(
                    data[matiere]['comps'][c]['note'] is not None for c in minfo['comps']
                ) else None
    # Maîtrise du palier
    mat_reussies = sum(1 for m in data.values() if m['mastery_matiere'] in ('Maxi', 'Mini'))
    if mat_reussies == 3:
        palier_mastery = 'Maxi'
    elif mat_reussies == 2:
        palier_mastery = 'Mini'
    elif mat_reussies == 1:
        palier_mastery = 'Part'
    else:
        palier_mastery = 'NM'
    return data, palier_mastery

@app.route('/bulletins')
@login_required
def bulletins():
    class_id = request.args.get('class_id')
    palier = request.args.get('palier', 'Palier 1')
    tc = teacher_class_filter()
    if tc:
        rooms = ClassRoom.query.filter_by(id=tc).all()
        selected = ClassRoom.query.get(tc)
    else:
        rooms = ClassRoom.query.order_by(ClassRoom.level).all()
        selected = ClassRoom.query.get(class_id) if class_id else (rooms[0] if rooms else None)
    students = Student.query.filter_by(class_id=selected.id).order_by(Student.last_name).all() if selected else []
    return render_template('bulletins.html', rooms=rooms, selected=selected,
                           students=students, palier=palier)

@app.route('/bulletins/<int:student_id>')
@login_required
def bulletin(student_id):
    student = Student.query.get_or_404(student_id)
    tc = teacher_class_filter()
    if tc and student.class_id != tc:
        flash('Accès réservé aux élèves de votre classe.', 'danger')
        return redirect(url_for('bulletins'))
    palier = request.args.get('palier', 'Palier 1')
    data, palier_mastery = compute_bulletin_data(student_id, palier)
    settings = SchoolSettings.query.first()
    return render_template('bulletin_detail.html', student=student, palier=palier,
                           data=data, palier_mastery=palier_mastery, settings=settings)

@app.route('/bulletins/<int:student_id>/pdf')
@login_required
def bulletin_pdf(student_id):
    """Bulletin officiel 2 pages — note critère 0-4, note compétence = somme"""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import mm, cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    from xml.sax.saxutils import escape as xml_escape

    student = Student.query.get_or_404(student_id)
    tc = teacher_class_filter()
    if tc and student.class_id != tc:
        flash('Accès réservé aux élèves de votre classe.', 'danger')
        return redirect(url_for('bulletins'))

    settings = SchoolSettings.query.first()
    level = student.classroom.level if student.classroom else '3ème année'
    annee = settings.annee_scolaire if settings else '2025-2026'

    all_paliers = ['Palier 1', 'Palier 2', 'Palier 3', 'Palier 4', 'Palier 5', 'Profil de sortie']
    palier_data = {}
    for p in all_paliers:
        d, pm = compute_bulletin_data(student_id, p)
        palier_data[p] = {'data': d, 'mastery': pm}

    buffer = io.BytesIO()
    # PAGE 1: portrait cover | PAGE 2: landscape grid
    # Build with two documents approach via landscape for page 2 only is hard in one flow
    # Use landscape for both for width of grid; page 1 content fits

    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            leftMargin=0.7*cm, rightMargin=0.7*cm,
                            topMargin=0.5*cm, bottomMargin=0.5*cm)
    styles = getSampleStyleSheet()
    tiny = ParagraphStyle('tiny', parent=styles['Normal'], fontSize=7, leading=9)
    small = ParagraphStyle('small', parent=styles['Normal'], fontSize=8.5, leading=11)
    title_s = ParagraphStyle('title_s', parent=styles['Normal'], fontSize=11,
                             alignment=TA_CENTER, fontName='Helvetica-Bold', spaceAfter=3)
    elements = []

    # ========== PAGE 1 : COUVERTURE ==========
    left_rules = """
<b>IDENTIFICATION DES DISCIPLINES À L'INTÉRIEUR DE CHAQUE COMPÉTENCE</b><br/><br/>
<b>ÉTUDE DU MILIEU ET ÉDUCATION ARTISTIQUE ET SPORTIVE (EDM&amp;EAS)</b><br/>
Compétence 1 : Histoire, Géographie, Éducation à la citoyenneté.<br/>
Compétence 2 : Biologie, Sciences physiques, Technologie, TIC.<br/>
Compétence 3 : Éducation artistique, Éducation physique et sportive.<br/><br/>
<b>MATHÉMATIQUES</b><br/>
Compétence 1 : Nombres et opérations, Résolution de problèmes.<br/>
Compétence 2 : Géométrie, Mesure.<br/><br/>
<b>FRANÇAIS</b><br/>
Compétence 1 : Production orale.<br/>
Compétence 2 : Lecture, Outils de la langue, Production écrite.<br/><br/>
<b>Règles de notation (bulletin officiel)</b><br/>
• Chaque <b>note de critère</b> est comprise entre <b>0 et 4</b>.<br/>
• La <b>note de la compétence</b> = somme des notes de critères (C1+C2+C3).<br/>
• <b>Maîtrise de la compétence</b> selon la note de compétence :<br/>
&nbsp;&nbsp;Maxi (8 à 12) · Mini (5 à 7) · Part (3 à 4) · NM (0 à 2)<br/>
• <b>Maîtrise de la matière</b> selon les maîtrises des compétences :<br/>
&nbsp;&nbsp;EDM (3 comp.) : Maxi 3/3 · Mini 2/3 · Part 1/3 · NM 0/3<br/>
&nbsp;&nbsp;Français / Maths (2 comp.) : Maxi 2/2 · Mini 1/2 · NM 0/2<br/>
• <b>Maîtrise du palier</b> : Maxi 3/3 matières · Mini 2/3 · Part 1/3 · NM 0/3<br/><br/>
<b>NB :</b> Bulletin à signer par l'enseignant(e), le (la) directeur(trice) et le parent/tuteur après chaque semaine d'intégration.
"""
    right_form = f"""
<b>MINISTÈRE DE L'ÉDUCATION NATIONALE</b><br/>
SECRÉTARIAT GÉNÉRAL<br/>
DIRECTION DE L'ENSEIGNEMENT PRIMAIRE<br/><br/>
<b>RÉPUBLIQUE GABONAISE</b><br/>
Union – Travail – Justice<br/>
Année Scolaire {annee}<br/><br/>
<b><font size="12">BULLETIN D'ÉVALUATION</font></b><br/>
Niveau : {level}<br/><br/>
DIRECTION D'ACADÉMIE PROVINCIALE DE : {settings.province if settings else '…………………'}<br/><br/>
CIRCONSCRIPTION OU SECTEUR SCOLAIRE DE : {settings.circonscription if settings else '…………………'}<br/><br/>
ÉCOLE : {settings.school_name if settings else '…………………'}<br/><br/>
Nom(s) et Prénom(s) de l'élève : <b>{xml_escape(student.full_name)}</b><br/><br/>
Statut : {'Nouveau ☑' if student.status == 'Nouveau' else 'Nouveau ☐'} &nbsp; {'Redoublant ☑' if student.status == 'Redoublant' else 'Redoublant ☐'}<br/><br/>
Nom de l'enseignant(e) : {student.classroom.teacher if student.classroom else '…………………'}<br/><br/>
Nom du (de la) directeur(trice) : {settings.director_name if settings else '…………………'}<br/><br/>
Matricule : {student.matricule or '—'}<br/>
Né(e) le : {student.birth_date.strftime('%d/%m/%Y') if student.birth_date else '—'} à {student.birth_place or '—'}
"""
    page1 = Table([[Paragraph(left_rules, tiny), Paragraph(right_form, small)]],
                  colWidths=[14.5*cm, 12.5*cm])
    page1.setStyle(TableStyle([
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('BOX', (0, 0), (0, 0), 0.6, colors.black),
        ('BOX', (1, 0), (1, 0), 1.5, colors.HexColor('#c026d3')),
        ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ('RIGHTPADDING', (0, 0), (-1, -1), 8),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (1, 0), (1, 0), colors.HexColor('#fdf4ff')),
    ]))
    elements.append(page1)
    elements.append(PageBreak())

    # ========== PAGE 2 : GRILLE ==========
    elements.append(Paragraph(
        f"ÉVALUATION FORMATIVE — {level} — {xml_escape(student.full_name)} — {annee}",
        title_s
    ))
    elements.append(Paragraph(
        "Note critère (0–4) · Note compétence = somme C1+C2+C3 · Maîtrise compétence / matière / palier",
        ParagraphStyle('n', parent=styles['Normal'], fontSize=7, alignment=TA_CENTER, spaceAfter=4)
    ))

    def c(txt, bold=False):
        st = ParagraphStyle('c', parent=styles['Normal'], fontSize=6.5, leading=8,
                            alignment=TA_CENTER, fontName='Helvetica-Bold' if bold else 'Helvetica')
        return Paragraph(str(txt) if txt is not None and txt != '' else '—', st)

    for palier_name in all_paliers:
        pd = palier_data[palier_name]
        data = pd['data']
        pm = pd['mastery'] or '—'

        header = [c(palier_name, True), c('C1', True), c('C2', True), c('C3', True),
                  c('Note comp.', True), c('Maîtrise comp.', True), c('Maîtrise matière', True)]
        rows = [header]
        color_map = []  # (row_index, col, mastery)

        for mat_key, minfo in COMPETENCES.items():
            mdata = data.get(mat_key, {})
            comps = list(minfo['comps'].items())
            for i, (comp, label) in enumerate(comps):
                cdata = mdata.get('comps', {}).get(comp, {})
                crits = cdata.get('crits', {})
                mc = cdata.get('mastery') or ''
                mast_mat = (mdata.get('mastery_matiere') or '') if i == 0 else ''
                rows.append([
                    c(f"{minfo['label'][:18]} — {comp}" if i == 0 else f"   {comp}: {label[:22]}"),
                    c(crits.get('c1') if crits.get('c1') is not None else ''),
                    c(crits.get('c2') if crits.get('c2') is not None else ''),
                    c(crits.get('c3') if crits.get('c3') is not None else ''),
                    c(cdata.get('note') if cdata.get('note') is not None else ''),
                    c(mc),
                    c(mast_mat),
                ])
                ri = len(rows) - 1
                if mc in ('Maxi', 'Mini', 'Part', 'NM'):
                    color_map.append((ri, 5, mc))
                if mast_mat in ('Maxi', 'Mini', 'Part', 'NM'):
                    color_map.append((ri, 6, mast_mat))
        # Ligne maîtrise du palier — pleine largeur + couleur vive
        pm_label = f'Maîtrise du palier (EDM, Français, Maths) :  {pm}'
        rows.append([c(pm_label, True), c(''), c(''), c(''), c(''), c(''), c('')])

        t = Table(rows, colWidths=[8*cm, 1.8*cm, 1.8*cm, 1.8*cm, 2.4*cm, 2.8*cm, 3*cm])
        last = len(rows) - 1
        pm_colors = {
            'Maxi': colors.HexColor('#16a34a'),
            'Mini': colors.HexColor('#0891b2'),
            'Part': colors.HexColor('#f59e0b'),
            'NM': colors.HexColor('#dc2626'),
        }
        bg_pm = pm_colors.get(pm, colors.HexColor('#fdf4ff'))
        style_cmds = [
            ('FONTSIZE', (0, 0), (-1, -1), 6.5),
            ('GRID', (0, 0), (-1, -1), 0.4, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#e879f9')),
            ('BACKGROUND', (0, last), (-1, last), bg_pm),
            ('TEXTCOLOR', (0, last), (-1, last), colors.white if pm in pm_colors else colors.black),
            ('ALIGN', (0, last), (-1, last), 'CENTER'),
            ('ALIGN', (1, 0), (-1, -2), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 2),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 2),
            ('TOPPADDING', (0, last), (-1, last), 5),
            ('BOTTOMPADDING', (0, last), (-1, last), 5),
        ]
        if last > 0:
            style_cmds.append(('SPAN', (0, last), (-1, last)))
        for ri, col, val in color_map:
            if val in pm_colors:
                style_cmds.append(('BACKGROUND', (col, ri), (col, ri), pm_colors[val]))
                style_cmds.append(('TEXTCOLOR', (col, ri), (col, ri), colors.white))
        t.setStyle(TableStyle(style_cmds))
        elements.append(t)
        elements.append(Spacer(1, 1.5*mm))

    vis = Table([
        [c('Visa Directeur(trice)', True), c('P1'), c('P2'), c('P3'), c('P4'), c('P5'),
         c('Décision du conseil de classe en fin d\'année', True)],
        [c('Visa Enseignant(e)', True), c(''), c(''), c(''), c(''), c(''), c('')],
        [c('Visa Parent / Tuteur', True), c(''), c(''), c(''), c(''), c(''), c('')],
    ], colWidths=[4.5*cm, 2*cm, 2*cm, 2*cm, 2*cm, 2*cm, 8.5*cm])
    vis.setStyle(TableStyle([
        ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('BACKGROUND', (0, 0), (0, -1), colors.HexColor('#fce7f3')),
    ]))
    elements.append(vis)

    try:
        doc.build(elements)
    except Exception as e:
        import traceback
        traceback.print_exc()
        flash(f'Erreur génération bulletin PDF : {e}', 'danger')
        return redirect(url_for('bulletins'))
    buffer.seek(0)
    safe_name = f"bulletin_{student.last_name}_{student.first_name}.pdf".replace(' ', '_')
    return send_file(buffer, mimetype='application/pdf',
                     as_attachment=True, download_name=safe_name)



def student_total_notes(data):
    """Somme des notes de compétence du palier pour classement"""
    total = 0
    for mat in data.values():
        for c in mat.get('comps', {}).values():
            if c.get('note') is not None:
                total += c['note']
    return total


def compute_palier_report(class_id, palier):
    """Rapport du palier + tableau d'honneur + meilleurs par discipline + stats G/F"""
    students = Student.query.filter_by(class_id=class_id).order_by(Student.last_name).all()
    rows = []
    for s in students:
        d, pm = compute_bulletin_data(s.id, palier)
        total = student_total_notes(d)
        sex = (s.gender or '').upper()
        if sex in ('M', 'MASCULIN', 'GARCON', 'G'):
            sex = 'G'
        elif sex in ('F', 'FEMININ', 'FILLE'):
            sex = 'F'
        else:
            sex = '?'
        rows.append({
            'student': s, 'data': d, 'palier_mastery': pm,
            'total': total, 'sex': sex
        })

    # Effectifs
    g_ins = sum(1 for r in rows if r['sex'] == 'G')
    f_ins = sum(1 for r in rows if r['sex'] == 'F')
    t_ins = len(rows)

    # Situations de réussite / échec au niveau PALIER
    # Réussite = Maxi ou Mini ; Échec = Part ou NM
    def count_mastery(level, sex=None):
        return sum(1 for r in rows
                   if r['palier_mastery'] == level
                   and (sex is None or r['sex'] == sex))

    maxi_g, maxi_f = count_mastery('Maxi', 'G'), count_mastery('Maxi', 'F')
    mini_g, mini_f = count_mastery('Mini', 'G'), count_mastery('Mini', 'F')
    part_g, part_f = count_mastery('Part', 'G'), count_mastery('Part', 'F')
    nm_g, nm_f = count_mastery('NM', 'G'), count_mastery('NM', 'F')

    reussite_g = maxi_g + mini_g
    reussite_f = maxi_f + mini_f
    echec_g = part_g + nm_g
    echec_f = part_f + nm_f
    reussite_t = reussite_g + reussite_f
    echec_t = echec_g + echec_f

    # Élèves avec au moins une note saisie
    evaluated = [r for r in rows if r['palier_mastery']]
    n_eval = len(evaluated) or 1
    pct_reussite = round(100 * reussite_t / n_eval, 1) if evaluated else 0
    pct_echec = round(100 * echec_t / n_eval, 1) if evaluated else 0

    # Maîtrise par matière / compétence (G F T)
    matiere_stats = {}
    for mat_key, minfo in COMPETENCES.items():
        matiere_stats[mat_key] = {'label': minfo['label'], 'comps': {}}
        for comp in minfo['comps']:
            counts = {
                'Maxi': {'G': 0, 'F': 0, 'T': 0},
                'Mini': {'G': 0, 'F': 0, 'T': 0},
                'Part': {'G': 0, 'F': 0, 'T': 0},
                'NM': {'G': 0, 'F': 0, 'T': 0},
            }
            for r in rows:
                m = r['data'].get(mat_key, {}).get('comps', {}).get(comp, {}).get('mastery')
                if m in counts:
                    if r['sex'] in ('G', 'F'):
                        counts[m][r['sex']] += 1
                    counts[m]['T'] += 1
            matiere_stats[mat_key]['comps'][comp] = counts

    # Tableau d'honneur : top 5 par total notes (parmi Maxi/Mini ou tous avec notes)
    honneur = sorted(
        [r for r in rows if r['total'] > 0],
        key=lambda r: (-r['total'], r['student'].last_name)
    )[:5]

    # Meilleurs par discipline (top 3)
    meilleurs = {}
    for mat_key, minfo in COMPETENCES.items():
        scored = []
        for r in rows:
            comps = r['data'].get(mat_key, {}).get('comps', {})
            notes = [c.get('note') for c in comps.values() if c.get('note') is not None]
            if notes:
                avg = sum(notes) / len(notes)
                scored.append({
                    'student': r['student'], 'sex': r['sex'],
                    'note': round(avg, 1),
                    'mastery': r['data'].get(mat_key, {}).get('mastery_matiere')
                })
        scored.sort(key=lambda x: (-x['note'], x['student'].last_name))
        meilleurs[mat_key] = scored[:3]

    return {
        'rows': rows,
        'effectifs': {'G': g_ins, 'F': f_ins, 'T': t_ins},
        'maxi': {'G': maxi_g, 'F': maxi_f, 'T': maxi_g + maxi_f},
        'mini': {'G': mini_g, 'F': mini_f, 'T': mini_g + mini_f},
        'part': {'G': part_g, 'F': part_f, 'T': part_g + part_f},
        'nm': {'G': nm_g, 'F': nm_f, 'T': nm_g + nm_f},
        'reussite': {'G': reussite_g, 'F': reussite_f, 'T': reussite_t},
        'echec': {'G': echec_g, 'F': echec_f, 'T': echec_t},
        'pct_reussite': pct_reussite,
        'pct_echec': pct_echec,
        'matiere_stats': matiere_stats,
        'honneur': honneur,
        'meilleurs': meilleurs,
        'n_eval': len(evaluated),
    }


def compute_recap_reussite(class_id):
    """Tableau récapitulatif des % de réussite sur tous les paliers + courbe"""
    paliers = ['Palier 1', 'Palier 2', 'Palier 3', 'Palier 4', 'Palier 5', 'Profil de sortie']
    recap = []
    for p in paliers:
        report = compute_palier_report(class_id, p)
        # Garçons/filles en réussite (Maxi+Mini)
        recap.append({
            'palier': p,
            'garcons': report['reussite']['G'],
            'filles': report['reussite']['F'],
            'total': report['reussite']['T'],
            'pct': report['pct_reussite'],
            'n_eval': report['n_eval'],
        })
    return recap


@app.route('/releves')
@login_required
def releves():
    """Liste des relevés de notes par classe + rapports automatiques"""
    class_id = request.args.get('class_id')
    palier = request.args.get('palier', 'Palier 1')
    tc = teacher_class_filter()
    if tc:
        rooms = ClassRoom.query.filter_by(id=tc).all()
        selected = ClassRoom.query.get(tc)
    else:
        rooms = ClassRoom.query.order_by(ClassRoom.level).all()
        selected = ClassRoom.query.get(class_id) if class_id else (rooms[0] if rooms else None)
    student_data = []
    report = None
    recap = None
    if selected:
        report = compute_palier_report(selected.id, palier)
        student_data = report['rows']
        recap = compute_recap_reussite(selected.id)
    return render_template('releves.html', rooms=rooms, selected=selected,
                           student_data=student_data, palier=palier,
                           report=report, recap=recap)


@app.route('/releves/pdf')
@login_required
def releves_pdf():
    """PDF relevé + rapport palier + honneur + récap"""
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    class_id = request.args.get('class_id', type=int)
    palier = request.args.get('palier', 'Palier 1')
    tc = teacher_class_filter()
    if tc and class_id != tc:
        flash('Accès réservé à votre classe.', 'danger')
        return redirect(url_for('releves'))
    room = ClassRoom.query.get_or_404(class_id)
    report = compute_palier_report(class_id, palier)
    recap = compute_recap_reussite(class_id)
    settings = SchoolSettings.query.first()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            leftMargin=0.8*cm, rightMargin=0.8*cm,
                            topMargin=0.6*cm, bottomMargin=0.6*cm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('t', parent=styles['Normal'], fontSize=11, alignment=TA_CENTER, fontName='Helvetica-Bold', spaceAfter=6)
    small = ParagraphStyle('s', parent=styles['Normal'], fontSize=7, alignment=TA_CENTER)
    elements = []

    def cell(txt, bold=False):
        st = ParagraphStyle('c', parent=styles['Normal'], fontSize=7, alignment=TA_CENTER,
                            fontName='Helvetica-Bold' if bold else 'Helvetica')
        return Paragraph(str(txt), st)

    # Page 1 - Rapport du palier
    elements.append(Paragraph(f"U nengue — RAPPORT DU {palier.upper()} — {room.name}", title))
    elements.append(Paragraph(f"{settings.school_name if settings else ''} — {settings.annee_scolaire if settings else ''}", small))
    elements.append(Spacer(1, 3*mm))

    r = report
    rows = [
        [cell('Effectifs', True), cell('G', True), cell('F', True), cell('T', True),
         cell('Maxi G', True), cell('Maxi F', True), cell('Maxi T', True),
         cell('Mini G', True), cell('Mini F', True), cell('Mini T', True),
         cell('Part G', True), cell('Part F', True), cell('Part T', True),
         cell('NM G', True), cell('NM F', True), cell('NM T', True)],
        [cell('Inscrits'), cell(r['effectifs']['G']), cell(r['effectifs']['F']), cell(r['effectifs']['T']),
         cell(r['maxi']['G']), cell(r['maxi']['F']), cell(r['maxi']['T']),
         cell(r['mini']['G']), cell(r['mini']['F']), cell(r['mini']['T']),
         cell(r['part']['G']), cell(r['part']['F']), cell(r['part']['T']),
         cell(r['nm']['G']), cell(r['nm']['F']), cell(r['nm']['T'])],
        [cell('% réussite', True), cell(''), cell(''), cell(f"{r['pct_reussite']}%", True),
         cell('% échec', True), cell(''), cell(f"{r['pct_echec']}%", True),
         cell(''), cell(''), cell(''), cell(''), cell(''), cell(''), cell(''), cell(''), cell('')],
    ]
    t = Table(rows, colWidths=[2.2*cm] + [1.5*cm]*15)
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c026d3')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (4, 1), (6, 1), colors.HexColor('#bbf7d0')),
        ('BACKGROUND', (7, 1), (9, 1), colors.HexColor('#a5f3fc')),
        ('BACKGROUND', (10, 1), (12, 1), colors.HexColor('#fde68a')),
        ('BACKGROUND', (13, 1), (15, 1), colors.HexColor('#fecaca')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 5*mm))

    # Honneur
    elements.append(Paragraph(f"TABLEAU D'HONNEUR DU {palier.upper()}", title))
    hrows = [[cell('Rang', True), cell('Nom et prénom', True), cell('Sexe', True),
              cell('Total notes', True), cell('Maîtrise palier', True)]]
    for i, h in enumerate(report['honneur'], 1):
        hrows.append([
            cell(f"{i}{'er' if i==1 else 'e'}"),
            cell(h['student'].full_name),
            cell(h['sex']),
            cell(h['total'], True),
            cell(h['palier_mastery'] or '—'),
        ])
    if len(hrows) == 1:
        hrows.append([cell('—'), cell('Aucune donnée'), cell(''), cell(''), cell('')])
    ht = Table(hrows, colWidths=[2*cm, 8*cm, 2*cm, 3*cm, 4*cm])
    ht.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c026d3')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
    ]))
    elements.append(ht)
    elements.append(PageBreak())

    # Recap %
    elements.append(Paragraph("TABLEAU RÉCAPITULATIF DES POURCENTAGES DE RÉUSSITE", title))
    header = [cell('', True)] + [cell(x['palier'], True) for x in recap]
    row_g = [cell('Garçons réussites', True)] + [cell(x['garcons']) for x in recap]
    row_f = [cell('Filles réussites', True)] + [cell(x['filles']) for x in recap]
    row_t = [cell('Total', True)] + [cell(x['total'], True) for x in recap]
    row_p = [cell('% réussite', True)] + [cell(f"{x['pct']}%", True) for x in recap]
    rt = Table([header, row_g, row_f, row_t, row_p], colWidths=[4*cm] + [3.5*cm]*len(recap))
    style = [
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.black),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c026d3')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#d1fae5')),
    ]
    rt.setStyle(TableStyle(style))
    elements.append(rt)
    elements.append(Spacer(1, 8*mm))
    elements.append(Paragraph(
        "Courbe de réussite : les pourcentages ci-dessus (Maxi+Mini / élèves évalués) servent de points pour P1 à Profil de sortie.",
        small
    ))

    doc.build(elements)
    buffer.seek(0)
    safe = f"releve_{room.name}_{palier}".replace(' ', '_').replace('è', 'e')
    return send_file(buffer, mimetype='application/pdf', as_attachment=True,
                     download_name=f"{safe}.pdf")




# ==================== CARTES SCOLAIRES ====================

@app.route('/cartes')
@login_required
def cartes():
    classes = ClassRoom.query.order_by(ClassRoom.level).all()
    return render_template('cartes.html', classes=classes)

@app.route('/cartes/classe/<int:id>')
@login_required
def cartes_classe(id):
    room = ClassRoom.query.get_or_404(id)
    students = Student.query.filter_by(class_id=id).order_by(Student.last_name).all()
    settings = SchoolSettings.query.first()
    return render_template('cartes_classe.html', room=room, students=students, settings=settings)

@app.route('/cartes/eleve/<int:id>')
@login_required
def carte_eleve(id):
    student = Student.query.get_or_404(id)
    settings = SchoolSettings.query.first()
    return render_template('carte_eleve.html', student=student, settings=settings)

# ==================== PARAMÈTRES ====================

@app.route('/parametres', methods=['GET', 'POST'])
@director_required
def parametres():
    settings = SchoolSettings.query.first()
    if request.method == 'POST':
        settings.school_name = request.form.get('school_name', settings.school_name)
        settings.address = request.form.get('address', '')
        settings.phone = request.form.get('phone', '')
        settings.email = request.form.get('email', '')
        settings.province = request.form.get('province', '')
        settings.circonscription = request.form.get('circonscription', '')
        settings.director_name = request.form.get('director_name', '')
        settings.annee_scolaire = request.form.get('annee_scolaire', '2025-2026')
        settings.sms_enabled = request.form.get('sms_enabled') == 'on'
        settings.sms_provider = request.form.get('sms_provider', 'twilio')
        settings.sms_account_sid = request.form.get('sms_account_sid', '')
        settings.sms_auth_token = request.form.get('sms_auth_token', '')
        settings.sms_from_number = request.form.get('sms_from_number', '')
        db.session.commit()
        flash('Paramètres mis à jour.', 'success')
        return redirect(url_for('parametres'))
    return render_template('parametres.html', settings=settings)


# ==================== RÉINSCRIPTION / PASSAGE DE CLASSE ====================

NEXT_LEVEL = {
    '1ère année': '2ème année',
    '2ème année': '3ème année',
    '3ème année': '4ème année',
    '4ème année': '5ème année',
    '5ème année': 'CEP',  # sortie primaire
}

def student_can_promote(student_id):
    """Vérifie si l'élève a au moins une maîtrise Mini sur les paliers 3,4,5"""
    ok_paliers = 0
    for palier in ['Palier 3', 'Palier 4', 'Palier 5']:
        data, pm = compute_bulletin_data(student_id, palier)
        if pm in ('Maxi', 'Mini'):
            ok_paliers += 1
    # Au moins maîtrise minimale sur paliers 3,4,5 (règle simplifiée)
    return ok_paliers >= 2

@app.route('/reinscription')
@director_required
def reinscription():
    """Page de fin d'année : réinscription et passages de classe"""
    settings = SchoolSettings.query.first()
    students = Student.query.order_by(Student.last_name).all()
    results = []
    for s in students:
        level = s.classroom.level if s.classroom else None
        can = student_can_promote(s.id) if level else False
        next_lv = NEXT_LEVEL.get(level) if level else None
        # Pour 5ème année : CEP admis si sélectionné + résultats OK
        if level == '5ème année':
            if s.cep_selected and can:
                decision = 'cep_admis'
                message = f'Félicitations 🎉💐 {s.full_name} ! Admission au CEP réussie. Bon courage pour le collège !'
            elif can:
                decision = 'redouble_ou_attente'
                message = 'Résultats suffisants mais non sélectionné CEP — à traiter manuellement'
            else:
                decision = 'redouble'
                message = 'Résultats insuffisants — redoublement en 5ème année'
        else:
            if can and next_lv:
                decision = 'promu'
                message = f'Félicitations 🎉💐 {s.full_name} ! Passage en {next_lv}.'
            else:
                decision = 'redouble'
                message = f'Redoublement en {level}'
        results.append({
            'student': s, 'level': level, 'next': next_lv,
            'can': can, 'decision': decision, 'message': message
        })
    return render_template('reinscription.html', results=results, settings=settings)

@app.route('/reinscription/appliquer', methods=['POST'])
@director_required
def appliquer_reinscription():
    """Applique les passages de classe sélectionnés"""
    settings = SchoolSettings.query.first()
    # Nouvelle année scolaire
    current = settings.annee_scolaire if settings else '2025-2026'
    try:
        y1, y2 = current.split('-')
        new_year = f"{int(y1)+1}-{int(y2)+1}"
    except:
        new_year = current
    if settings:
        settings.annee_scolaire = new_year

    selected_ids = request.form.getlist('student_id')
    messages = []
    for sid in selected_ids:
        s = Student.query.get(int(sid))
        if not s or not s.classroom:
            continue
        level = s.classroom.level
        can = student_can_promote(s.id)
        next_lv = NEXT_LEVEL.get(level)

        if level == '5ème année' and s.cep_selected and can:
            s.cep_admis = True
            s.status = 'Admis CEP'
            s.class_id = None  # sorti de l'école primaire
            messages.append(f'🎉 {s.full_name} — Admis au CEP, bon courage pour le collège !')
        elif can and next_lv and next_lv != 'CEP':
            # Trouver une classe du niveau suivant
            next_class = ClassRoom.query.filter_by(level=next_lv).first()
            if next_class:
                s.class_id = next_class.id
                s.status = 'Nouveau'
                s.annee_inscription = new_year
                messages.append(f'🎉💐 {s.full_name} — Passé en {next_lv}')
            else:
                messages.append(f'⚠️ {s.full_name} — Pas de classe {next_lv} disponible')
        else:
            s.status = 'Redoublant'
            s.annee_inscription = new_year
            messages.append(f'↻ {s.full_name} — Redouble en {level}')

    db.session.commit()
    for m in messages:
        flash(m, 'success')
    flash(f'Année scolaire mise à jour : {new_year}', 'info')
    return redirect(url_for('reinscription'))

@app.route('/reinscription/rechercher', methods=['GET', 'POST'])
@login_required
def rechercher_eleve():
    """Recherche un élève existant pour réinscription"""
    student = None
    message = None
    if request.method == 'POST':
        q = request.form.get('q', '').strip()
        student = Student.query.filter(
            db.or_(Student.matricule.ilike(f'%{q}%'),
                   Student.last_name.ilike(f'%{q}%'),
                   Student.first_name.ilike(f'%{q}%'))
        ).first()
        if student:
            level = student.classroom.level if student.classroom else None
            if student.cep_admis:
                message = f'🎓 {student.full_name} a été admis au CEP. Félicitations et bon courage pour le collège !'
            elif level:
                can = student_can_promote(student.id)
                next_lv = NEXT_LEVEL.get(level)
                if can and next_lv and next_lv != 'CEP':
                    message = f'🎉💐 {student.full_name} peut passer en {next_lv}. Félicitations !'
                elif level == '5ème année' and student.cep_selected and can:
                    message = f'🎉💐 {student.full_name} — Admission CEP réussie ! Bon courage pour le collège !'
                else:
                    message = f'{student.full_name} est actuellement en {level}. Résultats à vérifier pour le passage.'
            else:
                message = f'{student.full_name} trouvé (plus en classe).'
        else:
            flash('Aucun élève trouvé avec ces informations.', 'warning')
    return render_template('rechercher_eleve.html', student=student, message=message)

# ==================== GESTION DES ENSEIGNANTS ====================

@app.route('/enseignants')
@director_required
def enseignants():
    users = User.query.filter_by(role='Enseignant').all()
    classes = ClassRoom.query.order_by(ClassRoom.level).all()
    return render_template('enseignants.html', users=users, classes=classes)

@app.route('/enseignants/ajouter', methods=['POST'])
@director_required
def ajouter_enseignant():
    username = request.form.get('username', '').strip()
    password = request.form.get('password', '')
    full_name = request.form.get('full_name', '')
    class_id = request.form.get('class_id')
    if not username or not password:
        flash('Identifiant et mot de passe obligatoires.', 'danger')
        return redirect(url_for('enseignants'))
    if User.query.filter_by(username=username).first():
        flash('Cet identifiant existe déjà.', 'danger')
        return redirect(url_for('enseignants'))
    u = User(
        username=username,
        password_hash=generate_password_hash(password),
        full_name=full_name,
        role='Enseignant',
        class_id=int(class_id) if class_id else None
    )
    db.session.add(u)
    # Mettre à jour le nom de l'enseignant sur la classe
    if class_id:
        room = ClassRoom.query.get(int(class_id))
        if room:
            room.teacher = full_name
    db.session.commit()
    flash(f'Enseignant {full_name} créé. Identifiant : {username}', 'success')
    return redirect(url_for('enseignants'))

@app.route('/enseignants/<int:id>/supprimer')
@director_required
def supprimer_enseignant(id):
    u = User.query.get_or_404(id)
    if u.role == 'Directeur':
        flash('Impossible de supprimer le directeur.', 'danger')
    else:
        db.session.delete(u)
        db.session.commit()
        flash('Enseignant supprimé.', 'success')
    return redirect(url_for('enseignants'))


# ==================== MESSAGERIE INTERNE ====================

@app.route('/messages')
@login_required
def messages():
    uid = session['user_id']
    inbox = Message.query.filter_by(to_user_id=uid).order_by(Message.created_at.desc()).all()
    sent = Message.query.filter_by(from_user_id=uid).order_by(Message.created_at.desc()).all()
    # Destinataires possibles
    if session.get('role') == 'Directeur':
        contacts = User.query.filter_by(role='Enseignant').order_by(User.full_name).all()
    else:
        contacts = User.query.filter_by(role='Directeur').order_by(User.full_name).all()
    unread = Message.query.filter_by(to_user_id=uid, is_read=False).count()
    return render_template('messages.html', inbox=inbox, sent=sent, contacts=contacts, unread=unread)

@app.route('/messages/envoyer', methods=['POST'])
@login_required
def envoyer_message():
    to_id = request.form.get('to_user_id')
    subject = request.form.get('subject', '')
    body = request.form.get('body', '').strip()
    if not to_id or not body:
        flash('Destinataire et message obligatoires.', 'danger')
        return redirect(url_for('messages'))
    msg = Message(
        from_user_id=session['user_id'],
        to_user_id=int(to_id),
        subject=subject,
        body=body
    )
    db.session.add(msg)
    db.session.commit()
    flash('Message envoyé.', 'success')
    return redirect(url_for('messages'))

@app.route('/messages/<int:id>/lu')
@login_required
def message_lu(id):
    msg = Message.query.get_or_404(id)
    if msg.to_user_id == session['user_id']:
        msg.is_read = True
        db.session.commit()
    return redirect(url_for('messages'))

# ==================== WHATSAPP ====================

@app.route('/whatsapp')
@login_required
def whatsapp():
    tc = teacher_class_filter()
    if tc:
        classes = ClassRoom.query.filter_by(id=tc).all()
        students = Student.query.filter_by(class_id=tc).order_by(Student.last_name).all()
    else:
        classes = ClassRoom.query.order_by(ClassRoom.level, ClassRoom.name).all()
        students = Student.query.order_by(Student.last_name).all()
    return render_template('whatsapp.html', classes=classes, students=students)

@app.route('/whatsapp/preparer', methods=['POST'])
@login_required
def whatsapp_preparer():
    """Prépare les liens WhatsApp (individuel, classe ou école)"""
    mode = request.form.get('mode')  # individual, class, school
    message = request.form.get('message', '').strip()
    student_id = request.form.get('student_id')
    class_id = request.form.get('class_id')
    tc = teacher_class_filter()

    targets = []
    if mode == 'individual' and student_id:
        s = Student.query.get(int(student_id))
        if s and (not tc or s.class_id == tc):
            targets = [s]
    elif mode == 'class' and class_id:
        cid = int(class_id)
        if tc and tc != cid:
            flash('Accès réservé à votre classe.', 'danger')
            return redirect(url_for('whatsapp'))
        targets = Student.query.filter_by(class_id=cid).order_by(Student.last_name).all()
    elif mode == 'school':
        if session.get('role') != 'Directeur':
            flash('Seul le directeur peut écrire à toute l\'école.', 'danger')
            return redirect(url_for('whatsapp'))
        targets = Student.query.order_by(Student.last_name).all()
    else:
        flash('Sélection invalide.', 'warning')
        return redirect(url_for('whatsapp'))

    links = []
    for s in targets:
        if s.parent_phone:
            link = whatsapp_link(s.parent_phone, message)
            if link:
                links.append({
                    'student': s,
                    'phone': s.parent_phone,
                    'parent': s.parent_name or 'Parent',
                    'url': link
                })
    return render_template('whatsapp_liens.html', links=links, message=message, mode=mode)


# ==================== NOTIFICATIONS SMS ====================

@app.route('/sms')
@login_required
def sms_notifications():
    settings = SchoolSettings.query.first()
    tc = teacher_class_filter()
    if tc:
        classes = ClassRoom.query.filter_by(id=tc).all()
        students = Student.query.filter_by(class_id=tc).order_by(Student.last_name).all()
    else:
        classes = ClassRoom.query.order_by(ClassRoom.level, ClassRoom.name).all()
        students = Student.query.order_by(Student.last_name).all()
    logs = SmsLog.query.order_by(SmsLog.created_at.desc()).limit(50).all()
    return render_template('sms.html', classes=classes, students=students,
                           settings=settings, logs=logs)

@app.route('/sms/envoyer', methods=['POST'])
@login_required
def sms_envoyer():
    settings = SchoolSettings.query.first()
    mode = request.form.get('mode')
    body = request.form.get('message', '').strip()
    student_id = request.form.get('student_id')
    class_id = request.form.get('class_id')
    tc = teacher_class_filter()

    if not body:
        flash('Le message SMS est obligatoire.', 'danger')
        return redirect(url_for('sms_notifications'))

    targets = []
    if mode == 'individual' and student_id:
        s = Student.query.get(int(student_id))
        if s and (not tc or s.class_id == tc):
            targets = [s]
    elif mode == 'class' and class_id:
        cid = int(class_id)
        if tc and tc != cid:
            flash('Accès réservé à votre classe.', 'danger')
            return redirect(url_for('sms_notifications'))
        targets = Student.query.filter_by(class_id=cid).all()
    elif mode == 'school':
        if session.get('role') != 'Directeur':
            flash('Seul le directeur peut écrire à toute l\'école.', 'danger')
            return redirect(url_for('sms_notifications'))
        targets = Student.query.all()
    else:
        flash('Sélection invalide.', 'warning')
        return redirect(url_for('sms_notifications'))

    sent_ok = 0
    sent_fail = 0
    manual_links = []

    for s in targets:
        phone = s.parent_phone
        if not phone:
            continue
        num = normalize_phone_wa(phone)
        if settings and settings.sms_enabled and settings.sms_provider == 'twilio':
            ok, detail = send_sms_api(phone, body, settings)
            log = SmsLog(
                student_id=s.id, phone=phone,
                recipient_name=s.parent_name or s.full_name,
                body=body,
                status='sent' if ok else 'failed',
                error_message='' if ok else detail,
                sent_by=session.get('user_id')
            )
            db.session.add(log)
            if ok:
                sent_ok += 1
            else:
                sent_fail += 1
        else:
            # Mode manuel : lien sms: pour téléphone
            from urllib.parse import quote
            sms_url = f"sms:{num}?body={quote(body)}" if num else None
            log = SmsLog(
                student_id=s.id, phone=phone,
                recipient_name=s.parent_name or s.full_name,
                body=body, status='manual',
                sent_by=session.get('user_id')
            )
            db.session.add(log)
            if sms_url:
                manual_links.append({
                    'student': s, 'phone': phone,
                    'parent': s.parent_name or 'Parent',
                    'url': sms_url
                })
    db.session.commit()

    if settings and settings.sms_enabled and settings.sms_provider == 'twilio':
        flash(f'SMS : {sent_ok} envoyé(s), {sent_fail} échec(s).', 'success' if sent_ok else 'warning')
        return redirect(url_for('sms_notifications'))

    return render_template('sms_liens.html', links=manual_links, message=body)


# ==================== APPELS / PRÉSENCES ====================

@app.route('/appels')
@login_required
def appels():
    tc = teacher_class_filter()
    if tc:
        rooms = ClassRoom.query.filter_by(id=tc).all()
    else:
        rooms = ClassRoom.query.order_by(ClassRoom.level, ClassRoom.name).all()
    class_id = request.args.get('class_id', type=int) or (tc or (rooms[0].id if rooms else None))
    date_str = request.args.get('date', date.today().isoformat())
    try:
        selected = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        selected = date.today()
    hol, hol_label = is_holiday(selected)
    weekend = selected.weekday() >= 5
    students = Student.query.filter_by(class_id=class_id).order_by(Student.last_name).all() if class_id else []
    atts = {}
    if class_id:
        for a in Attendance.query.filter(
            Attendance.date == selected,
            Attendance.student_id.in_([s.id for s in students] or [0])
        ).all():
            atts[a.student_id] = a
    room = ClassRoom.query.get(class_id) if class_id else None
    freq = compute_frequentation(class_id) if class_id else None
    return render_template('appels.html', rooms=rooms, room=room, students=students,
                           selected=selected, atts=atts, is_holiday=hol, holiday_label=hol_label,
                           is_weekend=weekend, freq=freq)

@app.route('/appels/marquer', methods=['POST'])
@login_required
def appels_marquer():
    student_id = int(request.form.get('student_id'))
    date_str = request.form.get('date')
    status = request.form.get('status', 'Présent')
    selected = datetime.strptime(date_str, '%Y-%m-%d').date()
    student = Student.query.get_or_404(student_id)
    tc = teacher_class_filter()
    if tc and student.class_id != tc:
        flash('Accès réservé à votre classe.', 'danger')
        return redirect(url_for('appels'))
    if not is_school_day(selected):
        flash("Ce jour n'est pas un jour de classe (week-end ou ferie).", "warning")
        return redirect(url_for('appels', class_id=student.class_id, date=date_str))
    att = Attendance.query.filter_by(student_id=student_id, date=selected).first()
    if att:
        att.status = status
    else:
        db.session.add(Attendance(student_id=student_id, date=selected, status=status))
    db.session.commit()
    return redirect(url_for('appels', class_id=student.class_id, date=date_str))

@app.route('/appels/marquer-tous', methods=['POST'])
@login_required
def appels_marquer_tous():
    class_id = int(request.form.get('class_id'))
    date_str = request.form.get('date')
    status = request.form.get('status', 'Présent')
    selected = datetime.strptime(date_str, '%Y-%m-%d').date()
    tc = teacher_class_filter()
    if tc and tc != class_id:
        flash('Accès réservé à votre classe.', 'danger')
        return redirect(url_for('appels'))
    if not is_school_day(selected):
        flash('Jour non ouvrable.', 'warning')
        return redirect(url_for('appels', class_id=class_id, date=date_str))
    students = Student.query.filter_by(class_id=class_id).all()
    for s in students:
        att = Attendance.query.filter_by(student_id=s.id, date=selected).first()
        if att:
            att.status = status
        else:
            db.session.add(Attendance(student_id=s.id, date=selected, status=status))
    db.session.commit()
    flash(f'Tous marqués : {status}', 'success')
    return redirect(url_for('appels', class_id=class_id, date=date_str))

@app.route('/appels/stats')
@login_required
def appels_stats():
    tc = teacher_class_filter()
    if tc:
        rooms = ClassRoom.query.filter_by(id=tc).all()
    else:
        rooms = ClassRoom.query.order_by(ClassRoom.level).all()
    class_id = request.args.get('class_id', type=int) or (tc or (rooms[0].id if rooms else None))
    start_s = request.args.get('start', (date.today().replace(day=1)).isoformat())
    end_s = request.args.get('end', date.today().isoformat())
    start = datetime.strptime(start_s, '%Y-%m-%d').date()
    end = datetime.strptime(end_s, '%Y-%m-%d').date()
    stats = attendance_stats(class_id, start, end) if class_id else None
    room = ClassRoom.query.get(class_id) if class_id else None
    freq = compute_frequentation(class_id) if class_id else None
    return render_template('appels_stats.html', rooms=rooms, room=room, stats=stats,
                           start=start, end=end, freq=freq)

@app.route('/appels/recap')
@director_required
def appels_recap():
    """Tableau récapitulatif directeur — toutes les classes"""
    start_s = request.args.get('start', (date.today().replace(day=1)).isoformat())
    end_s = request.args.get('end', date.today().isoformat())
    start = datetime.strptime(start_s, '%Y-%m-%d').date()
    end = datetime.strptime(end_s, '%Y-%m-%d').date()
    rooms = ClassRoom.query.order_by(ClassRoom.level, ClassRoom.name).all()
    recap = []
    for r in rooms:
        st = attendance_stats(r.id, start, end)
        recap.append({'room': r, 'stats': st})
    return render_template('appels_recap.html', recap=recap, start=start, end=end)

@app.route('/appels/pdf')
@login_required
def appels_pdf():
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    class_id = request.args.get('class_id', type=int)
    start_s = request.args.get('start', (date.today().replace(day=1)).isoformat())
    end_s = request.args.get('end', date.today().isoformat())
    start = datetime.strptime(start_s, '%Y-%m-%d').date()
    end = datetime.strptime(end_s, '%Y-%m-%d').date()
    tc = teacher_class_filter()
    if tc and class_id != tc:
        flash('Accès réservé à votre classe.', 'danger')
        return redirect(url_for('appels_stats'))
    room = ClassRoom.query.get_or_404(class_id)
    stats = attendance_stats(class_id, start, end)
    settings = SchoolSettings.query.first()

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            leftMargin=1*cm, rightMargin=1*cm, topMargin=0.8*cm, bottomMargin=0.8*cm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('t', parent=styles['Normal'], fontSize=12, alignment=TA_CENTER, fontName='Helvetica-Bold')
    elements = [
        Paragraph(f"U nengue — Relevé d'appel — {room.name}", title),
        Paragraph(f"Période du {start.strftime('%d/%m/%Y')} au {end.strftime('%d/%m/%Y')} — "
                  f"Jours de classe : {stats['days']} — "
                  f"Présence classe : {stats['pct_presence']}% — Absence : {stats['pct_absence']}%",
                  ParagraphStyle('s', parent=styles['Normal'], fontSize=9, alignment=TA_CENTER, spaceAfter=8)),
    ]
    rows = [['N°', 'Élève', 'Présences', 'Absences', 'Retards', 'Jours marqués', '% Présence']]
    for i, r in enumerate(stats['students'], 1):
        rows.append([
            str(i), r['student'].full_name, str(r['present']), str(r['absent']),
            str(r['retard']), str(r['marked']),
            f"{r['pct_presence']}%" if r['pct_presence'] is not None else '—'
        ])
    t = Table(rows, colWidths=[1.5*cm, 7*cm, 2.5*cm, 2.5*cm, 2.5*cm, 3*cm, 3*cm])
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c026d3')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.black),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ]))
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=True,
                     download_name=f"appel_{room.name.replace(' ', '_')}.pdf")

@app.route('/jours-feries', methods=['GET', 'POST'])
@director_required
def jours_feries():
    if request.method == 'POST':
        d = request.form.get('date')
        label = request.form.get('label', 'Jour férié')
        if d:
            dd = datetime.strptime(d, '%Y-%m-%d').date()
            if not Holiday.query.filter_by(date=dd).first():
                db.session.add(Holiday(date=dd, label=label))
                db.session.commit()
                flash('Jour férié ajouté.', 'success')
        return redirect(url_for('jours_feries'))
    holidays = Holiday.query.order_by(Holiday.date.desc()).all()
    return render_template('jours_feries.html', holidays=holidays,
                           fixed=GABON_FIXED_HOLIDAYS)

@app.route('/jours-feries/<int:id>/supprimer')
@director_required
def supprimer_ferie(id):
    h = Holiday.query.get_or_404(id)
    db.session.delete(h)
    db.session.commit()
    flash('Jour férié supprimé.', 'success')
    return redirect(url_for('jours_feries'))

# ==================== CAHIER JOURNAL ====================

@app.route('/cahier-journal')
@login_required
def cahier_journal():
    tc = teacher_class_filter()
    if tc:
        rooms = ClassRoom.query.filter_by(id=tc).all()
    else:
        rooms = ClassRoom.query.order_by(ClassRoom.level).all()
    class_id = request.args.get('class_id', type=int) or (tc or (rooms[0].id if rooms else None))
    room = ClassRoom.query.get(class_id) if class_id else None
    entries = []
    if class_id:
        entries = ClassJournal.query.filter_by(class_id=class_id).order_by(
            ClassJournal.date.desc(), ClassJournal.id.desc()).limit(60).all()
    return render_template('cahier_journal.html', rooms=rooms, room=room, entries=entries, today=date.today().isoformat())

@app.route('/cahier-journal/ajouter', methods=['POST'])
@login_required
def cahier_ajouter():
    class_id = int(request.form.get('class_id'))
    tc = teacher_class_filter()
    if tc and tc != class_id:
        flash('Accès réservé à votre classe.', 'danger')
        return redirect(url_for('cahier_journal'))
    d = request.form.get('date') or date.today().isoformat()
    entry = ClassJournal(
        class_id=class_id,
        date=datetime.strptime(d, '%Y-%m-%d').date(),
        subject=request.form.get('subject', ''),
        content=request.form.get('content', ''),
        observation=request.form.get('observation', ''),
        author_id=session.get('user_id')
    )
    db.session.add(entry)
    db.session.commit()
    flash('Entrée du cahier journal enregistrée.', 'success')
    return redirect(url_for('cahier_journal', class_id=class_id))

@app.route('/cahier-journal/<int:id>/supprimer')
@login_required
def cahier_supprimer(id):
    entry = ClassJournal.query.get_or_404(id)
    tc = teacher_class_filter()
    if tc and entry.class_id != tc:
        flash('Accès refusé.', 'danger')
        return redirect(url_for('cahier_journal'))
    cid = entry.class_id
    db.session.delete(entry)
    db.session.commit()
    flash('Entrée supprimée.', 'success')
    return redirect(url_for('cahier_journal', class_id=cid))

@app.route('/cahier-journal/pdf')
@login_required
def cahier_pdf():
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    class_id = request.args.get('class_id', type=int)
    tc = teacher_class_filter()
    if tc and class_id != tc:
        flash('Accès réservé à votre classe.', 'danger')
        return redirect(url_for('cahier_journal'))
    room = ClassRoom.query.get_or_404(class_id)
    entries = ClassJournal.query.filter_by(class_id=class_id).order_by(ClassJournal.date.desc()).limit(40).all()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.2*cm, rightMargin=1.2*cm,
                            topMargin=1*cm, bottomMargin=1*cm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('t', parent=styles['Normal'], fontSize=12, alignment=TA_CENTER, fontName='Helvetica-Bold')
    small = ParagraphStyle('s', parent=styles['Normal'], fontSize=8, leading=10)
    elements = [Paragraph(f"U nengue — Cahier journal — {room.name}", title), Spacer(1, 6*mm)]
    for e in entries:
        block = f"""<b>{e.date.strftime('%d/%m/%Y')}</b> — {e.subject or '—'}<br/>
<b>Activités :</b> {(e.content or '—')[:500]}<br/>
<b>Observations :</b> {(e.observation or '—')[:400]}"""
        elements.append(Paragraph(block, small))
        elements.append(Spacer(1, 3*mm))
    if not entries:
        elements.append(Paragraph('Aucune entrée.', small))
    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=True,
                     download_name=f"cahier_journal_{room.name.replace(' ', '_')}.pdf")

@app.route('/classe/pdf')
@login_required
def classe_pdf():
    """Liste nominative PDF de la classe"""
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    class_id = request.args.get('class_id', type=int)
    tc = teacher_class_filter()
    if tc and class_id != tc:
        flash('Accès réservé à votre classe.', 'danger')
        return redirect(url_for('listes'))
    room = ClassRoom.query.get_or_404(class_id)
    students = Student.query.filter_by(class_id=class_id).order_by(Student.last_name).all()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.5*cm, rightMargin=1.5*cm)
    styles = getSampleStyleSheet()
    elements = [Paragraph(f"U nengue — Liste nominative — {room.name} ({room.level})",
                          ParagraphStyle('t', parent=styles['Normal'], fontSize=12,
                                         alignment=TA_CENTER, fontName='Helvetica-Bold', spaceAfter=10))]
    rows = [['N°', 'Nom et prénom', 'Matricule', 'Né(e) le', 'Lieu', 'Statut']]
    for i, s in enumerate(students, 1):
        rows.append([
            str(i), s.full_name, s.matricule or '—',
            s.birth_date.strftime('%d/%m/%Y') if s.birth_date else '—',
            s.birth_place or '—', s.status or '—'
        ])
    t = Table(rows, colWidths=[1.2*cm, 5*cm, 3*cm, 2.5*cm, 3*cm, 2.5*cm])
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c026d3')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.black),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
    ]))
    elements.append(t)
    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=True,
                     download_name=f"liste_{room.name.replace(' ', '_')}.pdf")


# ==================== THEMES ====================

THEMES = [
    ('fuchsia', 'Fuchsia Gabon'),
    ('mauve-spatial', 'Mauve spatial'),
    ('emeraude-mer', 'Émeraude & mer'),
    ('cristal-miranda', 'Cristal Miranda'),
    ('orange-vert', 'Orangé & vert'),
    ('soleil-or', 'Soleil d\'or'),
    ('nuit-indigo', 'Nuit indigo'),
    ('foret-okoume', 'Forêt okoumé'),
]

@app.route('/theme/<name>')
@login_required
def set_theme(name):
    allowed = {t[0] for t in THEMES}
    if name in allowed:
        session['theme'] = name
    return redirect(request.referrer or url_for('dashboard'))

# ==================== MON COMPTE / MOT DE PASSE ====================

@app.route('/mon-compte', methods=['GET', 'POST'])
@login_required
def mon_compte():
    user = User.query.get(session['user_id'])
    if request.method == 'POST':
        user.full_name = request.form.get('full_name', user.full_name)
        user.email = request.form.get('email', '')
        old = request.form.get('old_password', '')
        new = request.form.get('new_password', '')
        new2 = request.form.get('new_password2', '')
        if new:
            if not check_password_hash(user.password_hash, old):
                flash('Ancien mot de passe incorrect.', 'danger')
                return redirect(url_for('mon_compte'))
            if new != new2 or len(new) < 6:
                flash('Le nouveau mot de passe doit faire 6 caractères et être confirmé.', 'danger')
                return redirect(url_for('mon_compte'))
            user.password_hash = generate_password_hash(new)
            flash('Mot de passe modifié.', 'success')
        db.session.commit()
        session['full_name'] = user.full_name
        flash('Profil mis à jour.', 'success')
        return redirect(url_for('mon_compte'))
    return render_template('mon_compte.html', user=user)

@app.route('/mot-de-passe-oublie', methods=['GET', 'POST'])
def mot_de_passe_oublie():
    if request.method == 'POST':
        username = request.form.get('username', '').strip()
        user = User.query.filter_by(username=username).first()
        if not user:
            flash('Identifiant inconnu. Contactez le directeur.', 'danger')
            return render_template('mot_de_passe_oublie.html')
        import random, string
        code = ''.join(random.choices(string.digits, k=6))
        user.reset_code = code
        db.session.commit()
        flash(f'Code de réinitialisation pour {user.full_name} : {code}. '
              f'Sur un compte local, donnez ce code à l\'utilisateur (ou le directeur le communique).', 'info')
        return render_template('mot_de_passe_oublie.html', username=username, show_reset=True)
    return render_template('mot_de_passe_oublie.html')

@app.route('/mot-de-passe-reset', methods=['POST'])
def mot_de_passe_reset():
    username = request.form.get('username', '').strip()
    code = request.form.get('code', '').strip()
    new = request.form.get('new_password', '')
    new2 = request.form.get('new_password2', '')
    user = User.query.filter_by(username=username).first()
    if not user or not user.reset_code or user.reset_code != code:
        flash('Code invalide.', 'danger')
        return redirect(url_for('mot_de_passe_oublie'))
    if new != new2 or len(new) < 6:
        flash('Mot de passe trop court ou non confirmé.', 'danger')
        return redirect(url_for('mot_de_passe_oublie'))
    user.password_hash = generate_password_hash(new)
    user.reset_code = ''
    db.session.commit()
    flash('Mot de passe réinitialisé. Connectez-vous.', 'success')
    return redirect(url_for('login'))

@app.route('/enseignants/<int:id>/reset-mdp', methods=['POST'])
@director_required
def reset_mdp_enseignant(id):
    u = User.query.get_or_404(id)
    new = request.form.get('new_password') or 'enseignant123'
    u.password_hash = generate_password_hash(new)
    u.reset_code = ''
    db.session.commit()
    flash(f'Mot de passe de {u.full_name} réinitialisé : {new}', 'success')
    return redirect(url_for('enseignants'))

# ==================== ACTUALITÉS / PUBLICATIONS ====================

@app.route('/actualites')
@login_required
def actualites():
    items = Publication.query.order_by(Publication.created_at.desc()).all()
    return render_template('actualites.html', items=items)

@app.route('/actualites/ajouter', methods=['GET', 'POST'])
@director_required
def actualite_ajouter():
    if request.method == 'POST':
        title = request.form.get('title', '').strip()
        kind = request.form.get('kind', 'article')
        body = request.form.get('body', '')
        if not title:
            flash('Titre obligatoire.', 'danger')
            return redirect(url_for('actualite_ajouter'))
        filename = ''
        original = ''
        f = request.files.get('file')
        if f and f.filename:
            original = f.filename
            ext = original.rsplit('.', 1)[-1].lower()
            folder = os.path.join(app.config['UPLOAD_FOLDER'], 'publications')
            os.makedirs(folder, exist_ok=True)
            safe = f"{datetime.now().strftime('%Y%m%d%H%M%S')}_{secure_filename(original)}"
            f.save(os.path.join(folder, safe))
            filename = f'uploads/publications/{safe}'
        pub = Publication(title=title, kind=kind, body=body,
                          filename=filename, original_name=original,
                          author_id=session.get('user_id'))
        db.session.add(pub)
        db.session.commit()
        flash('Publication ajoutée.', 'success')
        return redirect(url_for('actualites'))
    return render_template('actualite_form.html')

@app.route('/actualites/<int:id>/supprimer')
@director_required
def actualite_supprimer(id):
    pub = Publication.query.get_or_404(id)
    db.session.delete(pub)
    db.session.commit()
    flash('Publication supprimée.', 'success')
    return redirect(url_for('actualites'))


# ==================== STATISTIQUES OFFICIELLES ====================

@app.route('/statistiques')
@login_required
def statistiques():
    """Tableaux officiels — directeur: toute l'école; enseignant: sa classe"""
    try:
        db.create_all()
        migrate_schema()
        tc = teacher_class_filter()
        class_id = request.args.get('class_id', type=int)
        if tc:
            class_id = tc
            rooms = ClassRoom.query.filter_by(id=tc).all()
        else:
            rooms = ClassRoom.query.order_by(ClassRoom.level).all()
        room = ClassRoom.query.get(class_id) if class_id else None
        stats = compute_class_stats(class_id)
        return render_template('statistiques.html', stats=stats, rooms=rooms, room=room, class_id=class_id)
    except Exception as e:
        flash(f'Erreur statistiques : {e}. Relancez après suppression de kyaf_edu.db si besoin.', 'danger')
        return redirect(url_for('dashboard'))

@app.route('/statistiques/pdf')
@login_required
def statistiques_pdf():
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.lib.units import cm, mm
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, PageBreak
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.enums import TA_CENTER

    tc = teacher_class_filter()
    class_id = request.args.get('class_id', type=int)
    if tc:
        class_id = tc
    room = ClassRoom.query.get(class_id) if class_id else None
    stats = compute_class_stats(class_id)
    settings = SchoolSettings.query.first()
    scope = room.name if room else 'École entière'

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.2*cm, rightMargin=1.2*cm,
                            topMargin=0.8*cm, bottomMargin=0.8*cm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('t', parent=styles['Normal'], fontSize=12, alignment=TA_CENTER,
                           fontName='Helvetica-Bold', spaceAfter=4, textColor=colors.HexColor('#7c3aed'))
    sub = ParagraphStyle('s', parent=styles['Normal'], fontSize=9, alignment=TA_CENTER, spaceAfter=8)
    elements = []

    def C(txt, bold=False):
        st = ParagraphStyle('c', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER,
                            fontName='Helvetica-Bold' if bold else 'Helvetica')
        return Paragraph(str(txt), st)

    def hdr_style(extra=None):
        base = [
            ('FONTSIZE', (0, 0), (-1, -1), 8),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c026d3')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
        ]
        if extra:
            base.extend(extra)
        return TableStyle(base)

    elements.append(Paragraph("U nengue — STATISTIQUES OFFICIELLES", title))
    elements.append(Paragraph(f"{settings.school_name if settings else ''} — {scope} — {stats['year_label']}", sub))

    # Répartition
    elements.append(Paragraph("TABLEAU DE RÉPARTITION DES ÉLÈVES", title))
    rp = stats['repartition']
    rows = [
        [C('Catégorie', True), C('Garçons', True), C('Filles', True), C('Total', True)],
        [C('Inscrits'), C(rp['inscrits']['G']), C(rp['inscrits']['F']), C(rp['inscrits']['T'], True)],
        [C('Nouveaux'), C(rp['nouveaux']['G']), C(rp['nouveaux']['F']), C(rp['nouveaux']['T'], True)],
        [C('Redoublants'), C(rp['redoublants']['G']), C(rp['redoublants']['F']), C(rp['redoublants']['T'], True)],
        [C('Primaux arrivés'), C(rp['primaux']['G']), C(rp['primaux']['F']), C(rp['primaux']['T'], True)],
        [C('Handicapés'), C(rp['handicapes']['G']), C(rp['handicapes']['F']), C(rp['handicapes']['T'], True)],
    ]
    t = Table(rows, colWidths=[5*cm, 3*cm, 3*cm, 3*cm])
    t.setStyle(hdr_style([('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#fdf4ff'))]))
    elements.append(t)
    elements.append(Spacer(1, 5*mm))

    # Nationalité
    elements.append(Paragraph("TABLEAU DE NATIONALITÉ", title))
    n = stats['nationalite']
    rows = [
        [C('Élèves gabonais', True), C('', True), C('', True), C('Élèves non-gabonais', True), C('', True), C('', True)],
        [C('Garçons', True), C('Filles', True), C('Total', True), C('Garçons', True), C('Filles', True), C('Total', True)],
        [C(n['gabonais']['G']), C(n['gabonais']['F']), C(n['gabonais']['T'], True),
         C(n['non_gabonais']['G']), C(n['non_gabonais']['F']), C(n['non_gabonais']['T'], True)],
    ]
    t = Table(rows, colWidths=[2.8*cm]*6)
    t.setStyle(TableStyle([
        ('FONTSIZE', (0, 0), (-1, -1), 8), ('GRID', (0, 0), (-1, -1), 0.5, colors.black),
        ('BACKGROUND', (0, 0), (2, 0), colors.HexColor('#16a34a')),
        ('BACKGROUND', (3, 0), (5, 0), colors.HexColor('#ea580c')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 1), (-1, 1), colors.HexColor('#f1f5f9')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'), ('SPAN', (0, 0), (2, 0)), ('SPAN', (3, 0), (5, 0)),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 5*mm))

    # Mobilité
    elements.append(Paragraph("MOBILITÉ GÉOGRAPHIQUE DES ÉLÈVES", title))
    rows = [[C('Provenance', True), C('Garçons', True), C('Filles', True), C('Total', True)]]
    for key, m in stats['mobilite'].items():
        rows.append([C(m['label'], key=='total'), C(m['G']), C(m['F']), C(m['T'], True)])
    t = Table(rows, colWidths=[8*cm, 2.5*cm, 2.5*cm, 2.5*cm])
    t.setStyle(hdr_style([('BACKGROUND', (0, -1), (-1, -1), colors.HexColor('#fde68a'))]))
    elements.append(t)
    elements.append(PageBreak())

    # Âges
    elements.append(Paragraph("RÉPARTITION PAR ÂGE DES ÉLÈVES", title))
    rows = [[C('Année de naissance', True), C('Garçons', True), C('Filles', True), C('Total', True), C('Âges', True)]]
    for a in stats['ages']:
        if a['T'] == 0 and a['age'] < 7:
            continue
        rows.append([C(a['birth_year']), C(a['G']), C(a['F']), C(a['T'], True), C(a['label'])])
    t = Table(rows, colWidths=[3.5*cm, 2.5*cm, 2.5*cm, 2.5*cm, 3*cm])
    t.setStyle(hdr_style())
    elements.append(t)
    elements.append(Spacer(1, 5*mm))

    # Effectifs mensuels
    elements.append(Paragraph("EFFECTIFS MENSUELS", title))
    rows = [[C('Mois', True), C('Garçons', True), C('Filles', True), C('Total', True)]]
    for m in stats['effectifs_mensuels']:
        if m.get('future'):
            rows.append([C(m['label']), C('—'), C('—'), C('—')])
        else:
            rows.append([C(m['label']), C(m['G']), C(m['F']), C(m['T'], True)])
    t = Table(rows, colWidths=[4*cm, 3*cm, 3*cm, 3*cm])
    t.setStyle(hdr_style())
    elements.append(t)
    elements.append(Spacer(1, 5*mm))

    # Manuels
    elements.append(Paragraph("MANUELS EN USAGE", title))
    rows = [[C('Discipline', True), C('Titre', True), C('Éditeur', True)]]
    for tb in stats['textbooks']:
        rows.append([C(tb.discipline), C(tb.title), C(tb.editor)])
    if len(rows) == 1:
        rows.append([C('—'), C('Aucun manuel enregistré'), C('—')])
    t = Table(rows, colWidths=[3.5*cm, 9*cm, 3*cm])
    t.setStyle(hdr_style())
    elements.append(t)

    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=True,
                     download_name=f"statistiques_{scope.replace(' ', '_')}.pdf")


@app.route('/manuels', methods=['GET', 'POST'])
@director_required
def manuels():
    if request.method == 'POST':
        d = request.form.get('discipline', '').strip()
        title = request.form.get('title', '').strip()
        editor = request.form.get('editor', 'IPN').strip()
        if d and title:
            db.session.add(Textbook(discipline=d, title=title, editor=editor))
            db.session.commit()
            flash('Manuel ajouté.', 'success')
        return redirect(url_for('manuels'))
    books = Textbook.query.order_by(Textbook.discipline).all()
    return render_template('manuels.html', books=books)

@app.route('/manuels/<int:id>/supprimer')
@director_required
def manuels_supprimer(id):
    b = Textbook.query.get_or_404(id)
    db.session.delete(b)
    db.session.commit()
    flash('Manuel supprimé.', 'success')
    return redirect(url_for('manuels'))

# ==================== INIT ====================

def init_db():
    with app.app_context():
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'photos'), exist_ok=True)
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'docs'), exist_ok=True)
        os.makedirs(os.path.join(app.config['UPLOAD_FOLDER'], 'publications'), exist_ok=True)
        db.create_all()
        migrate_schema()
        if not User.query.filter_by(username='admin').first():
            db.session.add(User(
                username='admin',
                password_hash=generate_password_hash('admin123'),
                full_name='Directeur(trice)',
                role='Directeur'
            ))
        if not SchoolSettings.query.first():
            db.session.add(SchoolSettings(
                school_name='École Publique Primaire',
                province='Estuaire',
                circonscription='Libreville',
                director_name='M./Mme le Directeur',
                annee_scolaire='2025-2026'
            ))
        if ClassRoom.query.count() == 0:
            for n in NIVEAUX:
                db.session.add(ClassRoom(name=f"{n} A", level=n, teacher=''))
                db.session.add(ClassRoom(name=f"{n} B", level=n, teacher=''))
        db.session.commit()
        if Student.query.count() == 0:
            c3 = ClassRoom.query.filter_by(level='3ème année').first()
            c5 = ClassRoom.query.filter_by(level='5ème année').first()
            demos = [
                ('MBINA', 'Jean-Pierre', '2016-03-15', 'Libreville', 'M', c3, 'Nouveau'),
                ('NZENGUE', 'Aisha', '2016-07-22', 'Port-Gentil', 'F', c3, 'Nouveau'),
                ('OBAME', 'Kevin', '2014-01-10', 'Franceville', 'M', c5, 'Nouveau'),
                ('MOUSSAVOU', 'Grace', '2014-11-05', 'Oyem', 'F', c5, 'Redoublant'),
            ]
            for last, first, bd, bp, gen, cls, st in demos:
                s = Student(
                    matricule=f"EPG-{last[:3]}{first[:2]}",
                    last_name=last, first_name=first,
                    birth_date=datetime.strptime(bd, '%Y-%m-%d').date(),
                    birth_place=bp, gender=gen, class_id=cls.id if cls else None,
                    parent_name=f"Parent {last}", parent_phone='077000000',
                    status=st
                )
                db.session.add(s)
            db.session.commit()
        print("Base de données initialisée (Primaire Gabon).")

# Initialisation au démarrage (local + Gunicorn / Render)
try:
    init_db()
except Exception as _e:
    print('startup init_db:', _e)

if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=debug)

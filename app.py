#!/usr/bin/env python3
"""
U nengue — Na buranghe ô dji icole di Gabu
École primaire gabonaise - 1ère à 5ème année
Système APC (Approche Par Compétences)
"""

from werkzeug.middleware.proxy_fix import ProxyFix
from itsdangerous import URLSafeTimedSerializer, BadSignature, SignatureExpired
from flask import (Flask, render_template, request, redirect, url_for,
                   flash, session, send_file, send_from_directory, jsonify)
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
app.url_map.strict_slashes = False
# Derrière Render / reverse proxy (HTTPS)
app.wsgi_app = ProxyFix(app.wsgi_app, x_for=1, x_proto=1, x_host=1, x_prefix=1)


# Sécurité : clé secrète depuis variable d'environnement en production
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'u-nengue-changez-moi-en-production-2026')
# Sessions stables (surtout sur Render HTTPS)
_is_render = bool(os.environ.get('RENDER') or os.environ.get('RENDER_EXTERNAL_URL'))
app.config['SESSION_COOKIE_HTTPONLY'] = True
app.config['SESSION_COOKIE_SAMESITE'] = 'Lax'
# Cookie sécurisé uniquement en HTTPS (Render)
app.config['SESSION_COOKIE_SECURE'] = _is_render or os.environ.get('SESSION_COOKIE_SECURE', '0') == '1'
app.config['PREFERRED_URL_SCHEME'] = 'https' if _is_render else 'http'
app.config['PERMANENT_SESSION_LIFETIME'] = int(os.environ.get('SESSION_LIFETIME', '604800'))  # 7 jours
app.config['SESSION_REFRESH_EACH_REQUEST'] = True
app.config['SESSION_COOKIE_NAME'] = 'unengue_session'
app.config['SESSION_COOKIE_PATH'] = '/'
app.config['SESSION_COOKIE_DOMAIN'] = None

_BASE_DIR = os.path.abspath(os.path.dirname(__file__))
_DB_PATH = os.path.join(_BASE_DIR, 'kyaf_edu.db')
_db_uri = os.environ.get('DATABASE_URL', '').strip()
if _db_uri.startswith('postgres://'):
    _db_uri = 'postgresql://' + _db_uri[len('postgres://'):]
# Forcer le driver psycopg2 (paquet psycopg2-binary)
if _db_uri.startswith('postgresql://') and '+psycopg' not in _db_uri:
    _db_uri = _db_uri.replace('postgresql://', 'postgresql+psycopg2://', 1)
app.config['SQLALCHEMY_DATABASE_URI'] = _db_uri or ('sqlite:///' + _DB_PATH)
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
app.config['UPLOAD_FOLDER'] = os.path.join(os.path.dirname(__file__), 'static', 'uploads')
app.config['MAX_CONTENT_LENGTH'] = 16 * 1024 * 1024  # 16 MB
app.config['PERMANENT_SESSION_LIFETIME'] = int(os.environ.get('SESSION_LIFETIME', '28800'))

db = SQLAlchemy(app)

from sqlalchemy import event as sa_event

@sa_event.listens_for(db.session, 'before_flush')
def _auto_tenant_before_flush(session, flush_context, instances):
    tid = None
    try:
        from flask import session as fs
        if fs.get('is_creator') and fs.get('view_tenant_id'):
            tid = fs.get('view_tenant_id')
        elif fs.get('tenant_id'):
            tid = fs.get('tenant_id')
    except Exception:
        return
    if tid is None:
        return
    for obj in session.new:
        if hasattr(obj, 'tenant_id') and getattr(obj, 'tenant_id', None) is None:
            if not getattr(obj, 'is_creator', False):
                try:
                    obj.tenant_id = tid
                except Exception:
                    pass



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

NIVEAUX = ['PS', 'MS', 'GS', '1ère année', '2ème année', '3ème année', '4ème année', '5ème année']
NIVEAUX_LABELS = {
    'PS': 'Petite section (PS)', 'MS': 'Moyenne section (MS)', 'GS': 'Grande section (GS)',
    '1ère année': '1ère année', '2ème année': '2ème année', '3ème année': '3ème année',
    '4ème année': '4ème année', '5ème année': '5ème année',
}
PREPRIMARY = ['PS', 'MS', 'GS']


SCHEDULE_DAYS = ['Lundi', 'Mardi', 'Mercredi', 'Jeudi', 'Vendredi']
SCHEDULE_SUBJECT_COLORS = {
    'Français': '#3b82f6',
    'Lecture': '#2563eb',
    'Production écrite': '#1d4ed8',
    'Mathématiques': '#ef4444',
    'Calcul': '#dc2626',
    'Géométrie': '#b91c1c',
    'Éveil scientifique': '#10b981',
    'Étude du milieu': '#059669',
    'Histoire': '#d97706',
    'Géographie': '#ca8a04',
    'Éducation civique': '#f59e0b',
    'Arts plastiques': '#ec4899',
    'Graphisme': '#db2777',
    'Musique': '#a855f7',
    'EPS': '#14b8a6',
    'Motricité': '#0d9488',
    'Anglais': '#6366f1',
    'Phonologie': '#8b5cf6',
    'Récréation': '#94a3b8',
    'Accueil': '#64748b',
    'Rituels': '#78716c',
    'Ateliers': '#f97316',
    'Religion': '#7c3aed',
    'Informatique': '#06b6d4',
}
DEFAULT_SCHEDULE_SUBJECTS = list(SCHEDULE_SUBJECT_COLORS.keys())

def subject_color(name):
    if not name:
        return '#c026d3'
    for k, v in SCHEDULE_SUBJECT_COLORS.items():
        if k.lower() in name.lower() or name.lower() in k.lower():
            return v
    # hash stable color
    colors = ['#c026d3','#3b82f6','#ef4444','#10b981','#f59e0b','#ec4899','#6366f1','#14b8a6','#f97316']
    return colors[sum(ord(c) for c in name) % len(colors)]

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


class Tenant(db.Model):
    """Compte école / établissement (multi-utilisateurs)"""
    id = db.Column(db.Integer, primary_key=True)
    school_name = db.Column(db.String(200), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    is_active = db.Column(db.Boolean, default=True)
    contact_email = db.Column(db.String(120), default='')
    contact_phone = db.Column(db.String(50), default='')
    province = db.Column(db.String(100), default='')
    users = db.relationship('User', backref='tenant', lazy=True)


class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    password_plain = db.Column(db.String(120), default='')  # visible UNIQUEMENT au créateur
    full_name = db.Column(db.String(120))
    email = db.Column(db.String(120), default='')
    role = db.Column(db.String(50), default='Directeur')  # Createur / Directeur / Enseignant
    is_creator = db.Column(db.Boolean, default=False)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class_room.id'), nullable=True)
    reset_code = db.Column(db.String(20), default='')
    classroom = db.relationship('ClassRoom', foreign_keys=[class_id])

class SchoolSettings(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True, index=True)
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
    # SMTP / e-mail
    smtp_enabled = db.Column(db.Boolean, default=False)
    smtp_host = db.Column(db.String(120), default='smtp.gmail.com')
    smtp_port = db.Column(db.Integer, default=587)
    smtp_user = db.Column(db.String(120), default='')
    smtp_password = db.Column(db.String(200), default='')
    smtp_from = db.Column(db.String(120), default='')
    smtp_use_tls = db.Column(db.Boolean, default=True)
    logo_path = db.Column(db.String(300), default='')
    logo2_path = db.Column(db.String(300), default='')
    logo3_path = db.Column(db.String(300), default='')
    logo4_path = db.Column(db.String(300), default='')

class ClassRoom(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True, index=True)
    name = db.Column(db.String(80), nullable=False)
    level = db.Column(db.String(30))  # 1ère année ... 5ème année
    teacher = db.Column(db.String(120))
    students = db.relationship('Student', backref='classroom', lazy=True)

class Student(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True, index=True)
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
    parent_pin = db.Column(db.String(20), default='')  # code espace parents
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
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True, index=True)
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
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True, index=True)
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
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True, index=True)
    title = db.Column(db.String(200), nullable=False)
    kind = db.Column(db.String(30), default='article')  # article, photo, document, video
    body = db.Column(db.Text, default='')
    filename = db.Column(db.String(300), default='')
    original_name = db.Column(db.String(200), default='')
    author_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    author = db.relationship('User')


class SongBank(db.Model):
    """Banque de comptines et chants (modifiable)."""
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True, index=True)
    titre = db.Column(db.String(200), nullable=False)
    niveau = db.Column(db.String(40), default='')  # PS, MS, GS, 1ère année...
    kind = db.Column(db.String(20), default='comptine')  # comptine | chant (évite conflit SQLAlchemy .type)
    texte = db.Column(db.Text, default='')
    source = db.Column(db.String(80), default='programme')  # programme | ecole | autre
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    @property
    def type(self):
        """Alias pour les templates existants."""
        return self.kind or 'comptine'

class Textbook(db.Model):
    """Manuels scolaires en usage"""
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True, index=True)
    discipline = db.Column(db.String(80), nullable=False)
    title = db.Column(db.String(250), nullable=False)
    editor = db.Column(db.String(120), default='IPN')
    level = db.Column(db.String(40), default='')  # optionnel: 5ème année...

class Holiday(db.Model):


    """Jours fériés / non ouvrés (école fermée)"""
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True, index=True)
    date = db.Column(db.Date, nullable=False, unique=True)
    label = db.Column(db.String(120), default='Jour férié')

class ClassJournal(db.Model):
    """Cahier journal par classe"""
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True, index=True)
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


class ScheduleSlot(db.Model):
    """Créneau d'emploi du temps par classe."""
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class_room.id'), nullable=False)
    day = db.Column(db.String(20), nullable=False)  # Lundi ... Vendredi
    start_time = db.Column(db.String(10), nullable=False)  # 08h00
    end_time = db.Column(db.String(10), nullable=False)    # 08h30
    subject = db.Column(db.String(120), nullable=False)
    teacher = db.Column(db.String(120), default='')
    color = db.Column(db.String(20), default='#c026d3')  # hex
    room = db.Column(db.String(80), default='')  # salle
    group_label = db.Column(db.String(40), default='')  # G1, G2, classe entière…
    notes = db.Column(db.String(200), default='')
    classroom = db.relationship('ClassRoom', backref=db.backref('schedule_slots', lazy=True, cascade='all, delete-orphan'))




class RitualSheet(db.Model):
    """Fiche journalière de rituels (plusieurs rituels le même jour)."""
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class_room.id'), nullable=True)
    date = db.Column(db.Date)
    # Anciens champs (1er rituel / compatibilité)
    duration = db.Column(db.String(40), default='')
    title = db.Column(db.String(200), default='')
    objective = db.Column(db.Text, default='')
    teacher_role = db.Column(db.Text, default='')
    student_role = db.Column(db.Text, default='')
    notes = db.Column(db.Text, default='')  # notes générales de la journée
    items_json = db.Column(db.Text, default='[]')  # liste de rituels
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    classroom = db.relationship('ClassRoom', backref=db.backref('ritual_sheets', lazy=True))

    def items(self):
        import json
        try:
            data = json.loads(self.items_json or '[]')
            if data:
                return data
        except Exception:
            pass
        # Compatibilité ancienne fiche à 1 rituel
        if self.title or self.duration or self.objective:
            return [{
                'duration': self.duration or '',
                'title': self.title or '',
                'objective': self.objective or '',
                'teacher_role': self.teacher_role or '',
                'student_role': self.student_role or '',
            }]
        return []

class PrepSheet(db.Model):
    """Fiche de préparation de séance (modèle officiel enrichi)."""
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class_room.id'), nullable=True)
    title = db.Column(db.String(250), default='')
    prerequisites = db.Column(db.Text, default='')
    competences = db.Column(db.Text, default='')
    general_objectives = db.Column(db.Text, default='')
    phase_comprehension = db.Column(db.Text, default='Mise en situation - Recherche - Mise en commun - Institutionnalisation')
    phase_automation = db.Column(db.Text, default='Structuration/entraînement (exercices, jeux, rituels…) + Évaluation et Remédiation')
    phase_reinvestment = db.Column(db.Text, default='')
    operational_objective = db.Column(db.Text, default='')
    core_competence = db.Column(db.Text, default='')
    opening = db.Column(db.Text, default='')
    scaffolding = db.Column(db.Text, default='')
    closing = db.Column(db.Text, default='')
    obstacles = db.Column(db.Text, default='')
    instruction = db.Column(db.Text, default='')  # consigne
    rows_json = db.Column(db.Text, default='[]')  # tableau séance
    subject = db.Column(db.String(80), default='')
    duration = db.Column(db.String(40), default='')
    teacher = db.Column(db.String(120), default='')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    classroom = db.relationship('ClassRoom', backref=db.backref('prep_sheets', lazy=True))

    def rows(self):
        import json
        try:
            return json.loads(self.rows_json or '[]')
        except Exception:
            return []

class PedagogicalSheet(db.Model):
    """Fiche pédagogique / fiche de préparation."""
    id = db.Column(db.Integer, primary_key=True)
    tenant_id = db.Column(db.Integer, db.ForeignKey('tenant.id'), nullable=True, index=True)
    class_id = db.Column(db.Integer, db.ForeignKey('class_room.id'), nullable=False)
    title = db.Column(db.String(200), default='')  # ex. Production d'écrits
    subject = db.Column(db.String(50), nullable=False)  # Français / Mathématiques / Éveil
    sub_discipline = db.Column(db.String(120), default='')  # libre
    duration = db.Column(db.String(30), default='30 min')
    domain = db.Column(db.String(120), default='')
    approach = db.Column(db.String(120), default='')  # Démarche
    notion = db.Column(db.String(200), default='')
    material = db.Column(db.String(300), default='')
    objective = db.Column(db.Text, default='')
    competence = db.Column(db.Text, default='')
    phases_json = db.Column(db.Text, default='[]')  # liste de phases
    written_trace = db.Column(db.Text, default='')
    teacher = db.Column(db.String(120), default='')
    created_by = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    updated_at = db.Column(db.DateTime, default=datetime.utcnow, onupdate=datetime.utcnow)
    classroom = db.relationship('ClassRoom', backref=db.backref('pedagogical_sheets', lazy=True))

    def phases(self):
        import json
        try:
            return json.loads(self.phases_json or '[]')
        except Exception:
            return []


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


def send_email(to_addr, subject, body_text, settings=None):
    """Envoie un e-mail via SMTP (Gmail, Outlook, etc.). Retourne (ok, message)."""
    import smtplib
    from email.mime.text import MIMEText
    from email.mime.multipart import MIMEMultipart
    if settings is None:
        settings = scoped_query(SchoolSettings).first()
    if not settings or not getattr(settings, 'smtp_enabled', False):
        return False, 'SMTP non activé dans Paramètres'
    host = (settings.smtp_host or '').strip()
    port = int(settings.smtp_port or 587)
    user = (settings.smtp_user or '').strip()
    password = (settings.smtp_password or '').strip()
    from_addr = (settings.smtp_from or user or '').strip()
    if not host or not user or not password or not to_addr:
        return False, 'Configuration SMTP incomplète'
    try:
        msg = MIMEMultipart()
        msg['From'] = from_addr
        msg['To'] = to_addr
        msg['Subject'] = subject
        msg.attach(MIMEText(body_text, 'plain', 'utf-8'))
        if getattr(settings, 'smtp_use_tls', True):
            server = smtplib.SMTP(host, port, timeout=30)
            server.ehlo()
            server.starttls()
            server.ehlo()
        else:
            server = smtplib.SMTP_SSL(host, port, timeout=30)
        server.login(user, password)
        server.sendmail(from_addr, [to_addr], msg.as_string())
        server.quit()
        return True, 'E-mail envoyé'
    except Exception as e:
        return False, str(e)

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
    h = scoped_query(Holiday).filter_by(date=d).first()
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
    students = scoped_query(Student).filter_by(class_id=class_id).all()
    days = school_days_between(start, end)
    if not students or not days:
        return {'students': [], 'pct_presence': 0, 'pct_absence': 0, 'days': 0}
    total_expected = 0
    total_present = 0
    total_absent = 0
    rows = []
    for s in students:
        atts = scoped_query(Attendance).filter(
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
    q = scoped_query(Student)
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
        'textbooks': scoped_query(Textbook).order_by(Textbook.discipline, Textbook.title).all() if 'textbook' in inspect_tables() else [],
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

        # Multi-tenant / colonnes manquantes (PostgreSQL : "user" est réservé → guillemets)
        dialect = db.engine.dialect.name  # 'postgresql' | 'sqlite'
        def qtable(t):
            return f'"{t}"' if dialect == 'postgresql' else t
        for table, col, coltype in [
            ('user', 'tenant_id', 'INTEGER'),
            ('user', 'is_creator', 'BOOLEAN DEFAULT FALSE'),
            ('user', 'password_plain', "VARCHAR(120) DEFAULT ''"),
            ('user', 'email', "VARCHAR(120) DEFAULT ''"),
            ('user', 'reset_code', "VARCHAR(20) DEFAULT ''"),
            ('class_room', 'tenant_id', 'INTEGER'),
            ('student', 'tenant_id', 'INTEGER'),
            ('school_settings', 'tenant_id', 'INTEGER'),
            ('publication', 'tenant_id', 'INTEGER'),
            ('message', 'tenant_id', 'INTEGER'),
            ('sms_log', 'tenant_id', 'INTEGER'),
            ('song_bank', 'tenant_id', 'INTEGER'),
            ('textbook', 'tenant_id', 'INTEGER'),
            ('holiday', 'tenant_id', 'INTEGER'),
            ('class_journal', 'tenant_id', 'INTEGER'),
            ('schedule_slot', 'tenant_id', 'INTEGER'),
            ('ritual_sheet', 'tenant_id', 'INTEGER'),
            ('prep_sheet', 'tenant_id', 'INTEGER'),
            ('pedagogical_sheet', 'tenant_id', 'INTEGER'),
        ]:
            try:
                names = insp.get_table_names()
                if table not in names:
                    continue
                cols = {c['name'] for c in insp.get_columns(table)}
                if col in cols:
                    continue
                sql = f'ALTER TABLE {qtable(table)} ADD COLUMN {col} {coltype}'
                with db.engine.begin() as conn:
                    conn.execute(sa_text(sql))
                print('migrate added', table, col)
            except Exception as e:
                print('migrate skip', table, col, e)
        # Force PostgreSQL critical columns even if inspect failed
        if dialect == 'postgresql':
            for sql in [
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS password_plain VARCHAR(120) DEFAULT ''',
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS is_creator BOOLEAN DEFAULT FALSE',
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS tenant_id INTEGER',
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS email VARCHAR(120) DEFAULT ''',
                'ALTER TABLE "user" ADD COLUMN IF NOT EXISTS reset_code VARCHAR(20) DEFAULT ''',
            ]:
                try:
                    with db.engine.begin() as conn:
                        conn.execute(sa_text(sql))
                except Exception as e:
                    print('pg force', e)

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


        try:
            cols = {c['name'] for c in insp.get_columns('student')}
            if 'parent_pin' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(sa_text("ALTER TABLE student ADD COLUMN parent_pin VARCHAR(20) DEFAULT ''"))
        except Exception:
            pass
        try:
            cols = {c['name'] for c in insp.get_columns('ritual_sheet')}
            if 'items_json' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(sa_text("ALTER TABLE ritual_sheet ADD COLUMN items_json TEXT DEFAULT '[]'"))
        except Exception:
            pass
        # schedule_slot group_label
        try:
            cols = {c['name'] for c in insp.get_columns('schedule_slot')}
            if 'group_label' not in cols:
                with db.engine.begin() as conn:
                    conn.execute(sa_text("ALTER TABLE schedule_slot ADD COLUMN group_label VARCHAR(40) DEFAULT ''"))
        except Exception:
            pass
        try:
            cols = {c['name'] for c in insp.get_columns('school_settings')}
            for col in ('logo_path', 'logo2_path', 'logo3_path', 'logo4_path'):
                if col not in cols:
                    try:
                        with db.engine.begin() as conn:
                            conn.execute(sa_text(f"ALTER TABLE school_settings ADD COLUMN {col} VARCHAR(300) DEFAULT ''"))
                    except Exception:
                        pass
        except Exception:
            pass

        # SMTP columns on school_settings
        try:
            cols = {c['name'] for c in insp.get_columns('school_settings')}
            for col, typ in [
                ('smtp_enabled', 'BOOLEAN DEFAULT 0'),
                ('smtp_host', "VARCHAR(120) DEFAULT 'smtp.gmail.com'"),
                ('smtp_port', 'INTEGER DEFAULT 587'),
                ('smtp_user', "VARCHAR(120) DEFAULT ''"),
                ('smtp_password', "VARCHAR(200) DEFAULT ''"),
                ('smtp_from', "VARCHAR(120) DEFAULT ''"),
                ('smtp_use_tls', 'BOOLEAN DEFAULT 1'),
            ]:
                if col not in cols:
                    try:
                        with db.engine.begin() as conn:
                            conn.execute(sa_text(f"ALTER TABLE school_settings ADD COLUMN {col} {typ}"))
                    except Exception:
                        pass
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


def _auth_serializer():
    return URLSafeTimedSerializer(app.config['SECRET_KEY'], salt='unengue-auth-v1')

def _set_auth_cookie(response, user_id):
    """Cookie d'auth de secours (7 jours) si la session Flask est perdue derrière le proxy Render."""
    try:
        token = _auth_serializer().dumps({'uid': int(user_id)})
        secure = bool(app.config.get('SESSION_COOKIE_SECURE'))
        response.set_cookie(
            'unengue_auth', token,
            max_age=7 * 24 * 3600,
            httponly=True,
            samesite='Lax',
            secure=secure,
            path='/',
        )
    except Exception as e:
        print('set_auth_cookie', e)
    return response

def _clear_auth_cookie(response):
    response.set_cookie('unengue_auth', '', max_age=0, path='/')
    return response

def _restore_session_from_cookie():
    """Si session vide, tente de restaurer depuis le cookie unengue_auth."""
    if session.get('user_id'):
        return True
    token = request.cookies.get('unengue_auth')
    if not token:
        return False
    try:
        data = _auth_serializer().loads(token, max_age=7 * 24 * 3600)
        uid = data.get('uid')
        user = User.query.get(uid) if uid else None
        if not user:
            return False
        session.permanent = True
        session['user_id'] = user.id
        session['username'] = user.username
        session['full_name'] = user.full_name or user.username
        session['role'] = user.role
        session['class_id'] = user.class_id
        session['tenant_id'] = user.tenant_id
        creator_name = os.environ.get('CREATOR_USERNAME', 'createur')
        session['is_creator'] = bool(
            getattr(user, 'is_creator', False)
            or user.role == 'Createur'
            or (user.username or '').lower() == creator_name.lower()
        )
        session.modified = True
        return True
    except (BadSignature, SignatureExpired, Exception) as e:
        print('restore_session', type(e).__name__)
        return False


def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            _restore_session_from_cookie()
        if not session.get('user_id'):
            flash('Veuillez vous connecter.', 'warning')
            nxt = request.full_path if request.query_string else request.path
            if nxt.endswith('?'):
                nxt = nxt[:-1]
            return redirect(url_for('login', next=nxt))
        session.modified = True
        return f(*args, **kwargs)
    return decorated

def director_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('user_id'):
            _restore_session_from_cookie()
        if not session.get('user_id'):
            flash('Veuillez vous connecter.', 'warning')
            return redirect(url_for('login'))
        if session.get('role') not in ('Directeur', 'Createur') and not session.get('is_creator'):
            flash('Accès réservé au directeur.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated


def creator_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if 'user_id' not in session:
            flash('Veuillez vous connecter.', 'warning')
            return redirect(url_for('login'))
        if not session.get('is_creator'):
            flash('Accès réservé au créateur de l\'application.', 'danger')
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

def current_tenant_id():
    """ID de l'école de l'utilisateur connecté (None pour le créateur hors impersonation)."""
    if session.get('is_creator'):
        return session.get('view_tenant_id')  # optionnel : voir une école
    return session.get('tenant_id')

def scoped_query(model):
    """Requêtes filtrées par école (base vide pour un nouveau compte)."""
    q = model.query
    if not hasattr(model, 'tenant_id'):
        return q
    if session.get('is_creator') and not session.get('view_tenant_id'):
        return q  # créateur voit tout
    tid = current_tenant_id()
    if tid is None:
        return q.filter(model.tenant_id == -1)  # rien
    return q.filter(model.tenant_id == tid)

def assign_tenant(obj):
    """Assigne le tenant_id à un nouvel objet."""
    if hasattr(obj, 'tenant_id') and obj.tenant_id is None:
        tid = current_tenant_id()
        if tid is not None:
            obj.tenant_id = tid
    return obj


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
            # --- Créateur de l'application (seul à voir tous les comptes) ---
            creator_user = os.environ.get('CREATOR_USERNAME', 'createur')
            creator_pwd = os.environ.get('CREATOR_PASSWORD', 'U-nengue-Createur-2026!')
            creator = User.query.filter_by(username=creator_user).first()
            if not creator:
                db.session.add(User(
                    username=creator_user,
                    password_hash=generate_password_hash(creator_pwd),
                    password_plain=creator_pwd,
                    full_name='Créateur U nengue — Mundziyi MABICKA',
                    role='Createur',
                    is_creator=True,
                    tenant_id=None,
                ))
                db.session.commit()
            else:
                creator.is_creator = True
                creator.role = 'Createur'
                if os.environ.get('RESET_CREATOR', '1') == '1':
                    creator.password_hash = generate_password_hash(creator_pwd)
                    creator.password_plain = creator_pwd
                db.session.commit()

            # Tenant par défaut + directeur démo (données existantes rattachées)
            default_tenant = db.session.query(Tenant).first()
            if not default_tenant:
                default_tenant = Tenant(school_name='École Publique Primaire (démo)', province='')
                db.session.add(default_tenant)
                db.session.commit()

            admin = User.query.filter_by(username='admin').first()
            force_pwd = os.environ.get('FORCE_ADMIN_PASSWORD', 'admin123')
            if not admin:
                db.session.add(User(
                    username='admin',
                    password_hash=generate_password_hash(force_pwd),
                    password_plain=force_pwd,
                    full_name='Directeur(trice)',
                    role='Directeur',
                    is_creator=False,
                    tenant_id=default_tenant.id,
                ))
                db.session.commit()
            else:
                if not admin.tenant_id:
                    admin.tenant_id = default_tenant.id
                if not admin.password_plain:
                    admin.password_plain = force_pwd if os.environ.get('RESET_ADMIN', '1') == '1' else admin.password_plain
                if os.environ.get('RESET_ADMIN', '1') == '1':
                    admin.password_hash = generate_password_hash(force_pwd)
                    admin.password_plain = force_pwd
                    admin.role = 'Directeur'
                    admin.is_creator = False
                db.session.commit()

            # Rattacher données sans tenant au tenant démo
            for Model in (ClassRoom, Student, SchoolSettings, Publication, Message):
                try:
                    db.session.query(Model).filter(Model.tenant_id.is_(None)).update({Model.tenant_id: default_tenant.id}, synchronize_session=False)
                except Exception:
                    pass
            db.session.commit()

            if not scoped_query(SchoolSettings).filter_by(tenant_id=default_tenant.id).first():
                db.session.add(SchoolSettings(
                    school_name='École Publique Primaire',
                    annee_scolaire='2025-2026',
                    tenant_id=default_tenant.id,
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
        settings = scoped_query(SchoolSettings).first()
        students_count = scoped_query(Student).count()
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
        username = (request.form.get('username') or '').strip()
        password = request.form.get('password') or ''
        role_choice = (request.form.get('role_choice') or '').strip()
        creator_name = os.environ.get('CREATOR_USERNAME', 'createur')
        user = None
        if username:
            user = User.query.filter_by(username=username).first()
            if not user:
                # recherche insensible à la casse
                user = User.query.filter(db.func.lower(User.username) == username.lower()).first()
            if not user and '@' in username:
                user = User.query.filter_by(email=username).first()
        ok = False
        if user and user.password_hash:
            try:
                ok = check_password_hash(user.password_hash, password)
            except Exception:
                ok = False
        # Secours : si le hash est cassé mais password_plain correspond (compte créateur/admin)
        if user and not ok and getattr(user, 'password_plain', None) and user.password_plain == password:
            user.password_hash = generate_password_hash(password)
            db.session.commit()
            ok = True
        if user and ok:
            # Le créateur peut se connecter avec n'importe quel profil coché
            is_c = bool(
                getattr(user, 'is_creator', False)
                or user.role == 'Createur'
                or (user.username or '').lower() == creator_name.lower()
            )
            if role_choice and user.role != role_choice and not is_c:
                # Ne bloque plus : ajuste juste le message si mauvais profil enseignant/directeur
                if user.role in ('Directeur', 'Enseignant') and role_choice in ('Directeur', 'Enseignant'):
                    flash(f'Attention : ce compte est « {user.role} ». Connexion quand même…', 'warning')
            session.permanent = True
            session['user_id'] = user.id
            session['username'] = user.username
            session['full_name'] = user.full_name or user.username
            session['role'] = user.role
            session['class_id'] = user.class_id
            session['tenant_id'] = user.tenant_id
            session['is_creator'] = is_c
            session.pop('view_tenant_id', None)
            flash(f'Bienvenue {session["full_name"]} ({user.role}) !', 'success')
            if session['is_creator']:
                resp = redirect(url_for('createur_panel_alias'))
            else:
                nxt = request.args.get('next') or request.form.get('next') or ''
                if nxt.startswith('/') and not nxt.startswith('//'):
                    resp = redirect(nxt)
                else:
                    resp = redirect(url_for('dashboard'))
            return _set_auth_cookie(resp, user.id)
        flash('Identifiant ou mot de passe incorrect. Essayez admin / admin123 ou createur / U-nengue-Createur-2026!', 'danger')
    return render_template('login.html')

@app.route('/logout', methods=['GET', 'POST'])
def logout():
    session.clear()
    resp = redirect(url_for('login'))
    resp = _clear_auth_cookie(resp)
    flash('Déconnexion réussie.', 'info')
    return resp


@app.route('/inscription', methods=['GET', 'POST'])
def inscription():
    """Création d'un nouveau compte école U nengue (base vide)."""
    if request.method == 'POST':
        school_name = (request.form.get('school_name') or '').strip()
        full_name = (request.form.get('full_name') or '').strip()
        username = (request.form.get('username') or '').strip().lower()
        password = request.form.get('password') or ''
        password2 = request.form.get('password2') or ''
        email = (request.form.get('email') or '').strip()
        phone = (request.form.get('phone') or '').strip()
        province = (request.form.get('province') or '').strip()
        if not school_name or not full_name or not username or not password:
            flash('Veuillez remplir tous les champs obligatoires.', 'danger')
            return render_template('inscription.html')
        if len(password) < 6:
            flash('Le mot de passe doit contenir au moins 6 caractères.', 'danger')
            return render_template('inscription.html')
        if password != password2:
            flash('Les mots de passe ne correspondent pas.', 'danger')
            return render_template('inscription.html')
        if User.query.filter_by(username=username).first():
            flash('Cet identifiant est déjà pris. Choisissez-en un autre.', 'danger')
            return render_template('inscription.html')
        if username in ('createur', 'admin'):
            flash('Cet identifiant est réservé.', 'danger')
            return render_template('inscription.html')
        tenant = Tenant(
            school_name=school_name,
            contact_email=email,
            contact_phone=phone,
            province=province,
            is_active=True,
        )
        db.session.add(tenant)
        db.session.flush()
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            password_plain=password,
            full_name=full_name,
            email=email,
            role='Directeur',
            is_creator=False,
            tenant_id=tenant.id,
        )
        db.session.add(user)
        db.session.add(SchoolSettings(
            school_name=school_name,
            annee_scolaire='2025-2026',
            director_name=full_name,
            phone=phone,
            email=email,
            province=province,
            tenant_id=tenant.id,
        ))
        db.session.commit()
        flash('Compte U nengue créé ! Votre base est vide et prête. Connectez-vous.', 'success')
        return redirect(url_for('login'))
    return render_template('inscription.html')


@app.route('/createur-panel', methods=['GET', 'POST', 'HEAD', 'OPTIONS'])
@creator_required
def createur_panel():
    """Panneau réservé au créateur : toutes les écoles et identifiants."""
    tenants = Tenant.query.order_by(Tenant.created_at.desc()).all()
    users = User.query.filter((User.is_creator == False) | (User.is_creator.is_(None))).order_by(User.tenant_id, User.username).all()
    by_tenant = {}
    for u in users:
        by_tenant.setdefault(u.tenant_id, []).append(u)
# --- Tableau de bord créateur (stats dynamiques) ---
    stats = {
        'nb_ecoles': len(tenants),
        'nb_users': len(users),
        'nb_directeurs': sum(1 for u in users if (u.role or '') == 'Directeur'),
        'nb_enseignants': sum(1 for u in users if (u.role or '') == 'Enseignant'),
        'nb_eleves_total': 0,
        'nb_classes_total': 0,
        'par_ecole': [],
    }
    try:
        stats['nb_eleves_total'] = Student.query.count()
        stats['nb_classes_total'] = ClassRoom.query.count()
    except Exception:
        pass
    for t in tenants:
        try:
            n_el = Student.query.filter_by(tenant_id=t.id).count()
            n_cl = ClassRoom.query.filter_by(tenant_id=t.id).count()
            n_us = len(by_tenant.get(t.id, []))
        except Exception:
            n_el = n_cl = n_us = 0
        stats['par_ecole'].append({
            'id': t.id,
            'nom': t.school_name,
            'province': t.province or '',
            'eleves': n_el,
            'classes': n_cl,
            'users': n_us,
        })
    total_el = stats['nb_eleves_total'] or 1
    for pe in stats['par_ecole']:
        pe['pct_eleves'] = round(100.0 * pe['eleves'] / total_el, 1) if stats['nb_eleves_total'] else 0
    if stats['nb_users']:
        stats['pct_directeurs'] = round(100.0 * stats['nb_directeurs'] / stats['nb_users'], 1)
        stats['pct_enseignants'] = round(100.0 * stats['nb_enseignants'] / stats['nb_users'], 1)
    else:
        stats['pct_directeurs'] = stats['pct_enseignants'] = 0
    return render_template('createur_panel.html', tenants=tenants, by_tenant=by_tenant, users=users, stats=stats)


@app.route('/createur/ecole/<int:tid>', methods=['GET', 'HEAD'])
@creator_required
def createur_voir_ecole(tid):
    """Le créateur consulte temporairement les données d'une école."""
    t = Tenant.query.get_or_404(tid)
    session['view_tenant_id'] = tid
    flash(f'Vous consultez l\'école : {t.school_name}', 'info')
    return redirect(url_for('dashboard'))


@app.route('/createur/quitter-ecole', methods=['GET', 'HEAD'])
@creator_required
def createur_quitter_ecole():
    session.pop('view_tenant_id', None)
    flash('Retour au panneau créateur.', 'info')
    return redirect(url_for('createur_panel_alias'))

@app.errorhandler(405)
def method_not_allowed(e):
    """Évite la page blanche 405."""
    # Tente de rester sur une page proche
    ref = request.path or ''
    flash("Cette action n'est pas disponible ainsi. Utilisez les boutons de la page.", "warning")
    if session.get('user_id'):
        if 'emploi' in ref:
            return redirect(url_for('emploi_du_temps'))
        if 'banque' in ref:
            return redirect(url_for('banque_activites'))
        if 'createur' in ref or 'panneau' in ref:
            return redirect(url_for('createur_panel_alias'))
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))






@app.route('/banque-activites', methods=['GET', 'HEAD', 'POST'])
@app.route('/banque-activités', methods=['GET', 'HEAD', 'POST'])
@login_required
def banque_activites():
    """Banque libre d'activités, exercices et évaluations illustrés."""
    items = list(BANQUE_ACTIVITES or [])
    niveau = (request.args.get('niveau') or '').strip()
    matiere = (request.args.get('matiere') or '').strip()
    type_ = (request.args.get('type') or '').strip()
    q = (request.args.get('q') or '').strip().lower()
    if niveau:
        items = [a for a in items if a.get('niveau') == niveau]
    if matiere:
        items = [a for a in items if a.get('matiere') == matiere]
    if type_:
        items = [a for a in items if a.get('type') == type_]
    if q:
        items = [a for a in items if q in (a.get('titre') or '').lower()
                 or q in (a.get('objectif') or '').lower()
                 or any(q in t.lower() for t in (a.get('tags') or []))]
    niveaux = sorted({a.get('niveau') for a in (BANQUE_ACTIVITES or []) if a.get('niveau')})
    matieres = sorted({a.get('matiere') for a in (BANQUE_ACTIVITES or []) if a.get('matiere')})
    pool = list(BANQUE_ACTIVITES or [])
    counts = {
        'activite': sum(1 for a in pool if a.get('type') == 'activite'),
        'exercice': sum(1 for a in pool if a.get('type') == 'exercice'),
        'evaluation': sum(1 for a in pool if a.get('type') == 'evaluation'),
    }
    return render_template(
        'banque_activites.html',
        items=items,
        niveaux=niveaux,
        matieres=matieres,
        niveau=niveau,
        matiere=matiere,
        type_=type_,
        q=q,
        total=len(pool),
        counts=counts,
    )


@app.route('/banque-activites/<int:aid>', methods=['GET', 'HEAD', 'POST'])
@app.route('/banque-activités/<int:aid>', methods=['GET', 'HEAD', 'POST'])
@login_required
def banque_activite_detail(aid):
    try:
        pool = list(BANQUE_ACTIVITES or [])
    except Exception:
        pool = []
    act = next((a for a in pool if int(a.get('id', -1)) == int(aid)), None)
    if not act:
        flash('Activité introuvable.', 'warning')
        return redirect(url_for('banque_activites'))
    vis = act.get('visual') or {}
    bar_max = 1
    if vis.get('type') == 'svg_bars':
        vals = [b.get('value') or 0 for b in (vis.get('bars') or [])]
        bar_max = max(vals) if vals else 1
    return render_template('banque_activite_detail.html', act=act, bar_max=bar_max)


@app.route('/api/activite/<int:aid>/texte', methods=['GET'])
@login_required
def api_activite_texte(aid):
    """Texte prêt à coller dans une fiche de préparation."""
    act = next((a for a in (BANQUE_ACTIVITES or []) if int(a.get('id', -1)) == int(aid)), None)
    if not act:
        return jsonify({'ok': False}), 404
    lines = [
        f"【{(act.get('type') or 'activité').upper()}】 {act.get('titre')}",
        f"Niveau : {act.get('niveau')} — Matière : {act.get('matiere')} — Durée : {act.get('duree_min', '')} min",
        f"Objectif : {act.get('objectif')}",
    ]
    if act.get('situation'):
        lines.append("Situation-problème :")
        lines.append(act.get('situation'))
    if act.get('materiel'):
        lines.append("Matériel : " + ", ".join(act.get('materiel') or []))
    if act.get('phases'):
        lines.append("Phases :")
        for p in act.get('phases') or []:
            lines.append(f" • {p.get('nom', '')} ({p.get('duree', '')}) : {p.get('description', '')}")
    else:
        lines.append("Déroulement :")
        for d in act.get('deroule') or []:
            lines.append(f" • {d}")
    if act.get('role_enseignant'):
        lines.append("Rôle enseignant : " + " / ".join(act.get('role_enseignant') or []))
    if act.get('role_eleve'):
        lines.append("Rôle élève : " + " / ".join(act.get('role_eleve') or []))
    lines.append("Consignes élèves :")
    for c in act.get('consignes') or []:
        lines.append(f" • {c}")
    if act.get('correction'):
        lines.append(f"Correction / critères : {act.get('correction')}")
    if act.get('differenciation'):
        lines.append(f"Différenciation : {act.get('differenciation')}")
    if act.get('trace_ecrite'):
        lines.append(f"Trace écrite : {act.get('trace_ecrite')}")
    return jsonify({'ok': True, 'texte': '\n'.join(lines), 'titre': act.get('titre')})


# ==================== DASHBOARD ====================

@app.route('/')
@login_required
def dashboard():
    settings = scoped_query(SchoolSettings).first()
    total = scoped_query(Student).count()
    classes = scoped_query(ClassRoom).count()
    cep_count = scoped_query(Student).filter_by(cep_selected=True).count()
    by_level = []
    for n in NIVEAUX:
        c = scoped_query(Student).join(ClassRoom).filter(ClassRoom.level == n).count()
        by_level.append((n, c))
    recent = scoped_query(Student).order_by(Student.created_at.desc()).limit(5).all()
    try:
        news = scoped_query(Publication).order_by(Publication.created_at.desc()).limit(6).all()
    except Exception:
        news = []
    all_s = scoped_query(Student).all()
    gender_counts = gft(all_s) if all_s else {'G': 0, 'F': 0, 'T': 0}
    max_level = max([c for _, c in by_level], default=1) or 1
    import random
    quote_jour = QUOTES_JOUR[datetime.now().timetuple().tm_yday % len(QUOTES_JOUR)]
    try:
        upcoming_holidays = scoped_query(Holiday).filter(Holiday.date >= datetime.utcnow().date()).order_by(Holiday.date).limit(5).all()
    except Exception:
        upcoming_holidays = []
    return render_template('dashboard.html', total=total, classes=classes,
                           cep_count=cep_count, by_level=by_level, recent=recent,
                           news=news, gender_counts=gender_counts, max_level=max_level, quote_jour=quote_jour, upcoming_holidays=upcoming_holidays)

# ==================== ÉLÈVES ====================

@app.route('/eleves', methods=['GET', 'HEAD'])
@login_required
def eleves():
    q = request.args.get('q', '')
    class_filter = request.args.get('class_id', '')
    level_filter = request.args.get('level', '')
    sort = request.args.get('sort', 'name')  # name, matricule, class, status, birth
    order = request.args.get('order', 'asc')
    query = scoped_query(Student)
    tc = teacher_class_filter()
    if tc:
        query = query.filter_by(class_id=tc)
        class_filter = str(tc)
    if q:
        query = query.filter(
            db.or_(Student.last_name.ilike(f'%{q}%'),
                   Student.first_name.ilike(f'%{q}%'),
                   Student.matricule.ilike(f'%{q}%'),
                   Student.parent_name.ilike(f'%{q}%'))
        )
    if class_filter and not tc:
        try:
            query = query.filter_by(class_id=int(class_filter))
        except Exception:
            pass
    if level_filter and not tc:
        query = query.join(ClassRoom).filter(ClassRoom.level == level_filter)
    # tri
    col = Student.last_name
    if sort == 'matricule':
        col = Student.matricule
    elif sort == 'status':
        col = Student.status
    elif sort == 'birth':
        col = Student.birth_date
    elif sort == 'class':
        query = query.outerjoin(ClassRoom)
        col = ClassRoom.name
    if order == 'desc':
        col = col.desc()
    else:
        col = col.asc()
    students = query.order_by(col).all()
    if tc:
        classes = scoped_query(ClassRoom).filter_by(id=tc).all()
    else:
        classes = scoped_query(ClassRoom).order_by(ClassRoom.level, ClassRoom.name).all()
    return render_template('eleves.html', students=students, classes=classes,
                           q=q, class_filter=class_filter, level_filter=level_filter,
                           sort=sort, order=order)

@app.route('/eleves/ajouter', methods=['GET', 'POST'])
@director_required
def ajouter_eleve():
    classes = scoped_query(ClassRoom).order_by(ClassRoom.level).all()
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
    student = scoped_query(Student).filter_by(id=id).first()
    if not student:
        flash('Élève introuvable ou hors de votre école.', 'danger')
        return redirect(url_for('eleves'))
    classes = scoped_query(ClassRoom).order_by(ClassRoom.level).all()
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
        student.parent_pin = request.form.get('parent_pin', '').strip()
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

@app.route('/eleves/<int:id>', methods=['GET', 'HEAD'])
@login_required
def fiche_eleve(id):
    student = scoped_query(Student).get_or_404(id)
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

    student = scoped_query(Student).get_or_404(id)
    tc = teacher_class_filter()
    if tc and student.class_id != tc:
        flash('Accès réservé aux élèves de votre classe.', 'danger')
        return redirect(url_for('eleves'))
    settings = scoped_query(SchoolSettings).first()

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


@app.route('/eleves/<int:id>/supprimer', methods=['GET', 'POST'])
@director_required
def supprimer_eleve(id):
    """Supprimer un élève (GET confirmé ou POST)."""
    student = scoped_query(Student).filter_by(id=id).first()
    if not student:
        flash('Élève introuvable ou hors de votre école.', 'danger')
        return redirect(url_for('eleves'))
    tc = teacher_class_filter()
    if tc and student.class_id != tc:
        flash('Accès réservé aux élèves de votre classe.', 'danger')
        return redirect(url_for('eleves'))
    if session.get('role') == 'Enseignant':
        flash('Seuls le directeur peut supprimer un élève.', 'danger')
        return redirect(url_for('eleves'))
    name = getattr(student, 'full_name', None) or f'{student.last_name} {student.first_name}'
    try:
        Evaluation.query.filter_by(student_id=id).delete()
        Attendance.query.filter_by(student_id=id).delete()
        try:
            StudentDocument.query.filter_by(student_id=id).delete()
        except Exception:
            pass
        db.session.delete(student)
        db.session.commit()
        flash(f'Élève {name} supprimé.', 'success')
    except Exception as e:
        db.session.rollback()
        flash(f'Erreur suppression : {e}', 'danger')
    return redirect(url_for('eleves'))


@app.route('/eleves/supprimer-tous', methods=['GET', 'POST'])
@director_required
def supprimer_tous_eleves():
    scoped_query(Evaluation).delete()
    scoped_query(Attendance).delete()
    StudentDocument.query.delete()
    n = scoped_query(Student).delete()
    db.session.commit()
    flash(f'Fichier nominatif effacé : {n} élève(s) supprimé(s).', 'success')
    return redirect(url_for('listes'))

# ==================== LISTES NOMINATIVES ====================

@app.route('/listes', methods=['GET', 'HEAD'])
@login_required
def listes():
    tc = teacher_class_filter()
    if tc:
        classes = scoped_query(ClassRoom).filter_by(id=tc).all()
        all_students = scoped_query(Student).filter_by(class_id=tc).order_by(Student.last_name).all()
    else:
        classes = scoped_query(ClassRoom).order_by(ClassRoom.level, ClassRoom.name).all()
        all_students = scoped_query(Student).order_by(Student.last_name).all()
    return render_template('listes.html', classes=classes, all_students=all_students)

@app.route('/listes/classe/<int:id>', methods=['GET', 'HEAD'])
@login_required
def liste_classe(id):
    """Liste nominative d'une classe (tri nom, accessible directeur / enseignant de la classe)."""
    room = scoped_query(ClassRoom).filter_by(id=id).first()
    if not room:
        flash('Classe introuvable.', 'danger')
        return redirect(url_for('listes'))
    tc = teacher_class_filter()
    if tc and tc != id:
        flash('Accès réservé à votre classe uniquement.', 'danger')
        return redirect(url_for('listes'))
    students = (
        scoped_query(Student)
        .filter_by(class_id=id)
        .order_by(Student.last_name.asc(), Student.first_name.asc())
        .all()
    )
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
    students = scoped_query(Student).join(ClassRoom).filter(
        ClassRoom.level == '5ème année'
    ).order_by(Student.last_name).all()
    return render_template('cep.html', students=students)

@app.route('/cep/toggle/<int:id>')
@director_required
def cep_toggle(id):
    student = scoped_query(Student).get_or_404(id)
    student.cep_selected = not student.cep_selected
    db.session.commit()
    flash(f"{student.full_name} {'sélectionné' if student.cep_selected else 'retiré'} pour le CEP.", 'success')
    return redirect(url_for('cep'))

@app.route('/cep/candidats')
@director_required
def cep_candidats():
    """Liste nominative + relevé de notes des candidats CEP"""
    candidats = scoped_query(Student).filter_by(cep_selected=True).order_by(Student.last_name).all()
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
    settings = scoped_query(SchoolSettings).first()
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

    candidats = scoped_query(Student).filter_by(cep_selected=True).order_by(Student.last_name).all()
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
    settings = scoped_query(SchoolSettings).first()
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
    rooms = scoped_query(ClassRoom).order_by(ClassRoom.level, ClassRoom.name).all()
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
    room = scoped_query(ClassRoom).get_or_404(id)
    if request.method == 'POST':
        room.name = request.form.get('name')
        room.level = request.form.get('level')
        room.teacher = request.form.get('teacher')
        db.session.commit()
        flash('Classe mise à jour.', 'success')
        return redirect(url_for('classes'))
    return render_template('classe_form.html', room=room)

@app.route('/classes/<int:id>/supprimer', methods=['GET', 'POST'])
@director_required
def supprimer_classe(id):
    room = scoped_query(ClassRoom).get_or_404(id)
    name = room.name
    # Supprimer tous les élèves de la classe d'abord
    for s in list(room.students):
        scoped_query(Evaluation).filter_by(student_id=s.id).delete()
        scoped_query(Attendance).filter_by(student_id=s.id).delete()
        StudentDocument.query.filter_by(student_id=s.id).delete()
        db.session.delete(s)
    db.session.delete(room)
    db.session.commit()
    flash(f'Classe {name} et ses élèves supprimés.', 'success')
    return redirect(url_for('classes'))

@app.route('/classes/<int:id>/vider', methods=['GET', 'POST'])
@director_required
def vider_classe(id):
    room = scoped_query(ClassRoom).get_or_404(id)
    n = 0
    for s in list(room.students):
        scoped_query(Evaluation).filter_by(student_id=s.id).delete()
        scoped_query(Attendance).filter_by(student_id=s.id).delete()
        StudentDocument.query.filter_by(student_id=s.id).delete()
        db.session.delete(s)
        n += 1
    db.session.commit()
    flash(f'{n} élève(s) retiré(s) de la classe {room.name}.', 'success')
    return redirect(url_for('classes'))

# ==================== ÉVALUATIONS / NOTES ====================

@app.route('/evaluations', methods=['GET', 'HEAD'])
@login_required
def evaluations():
    class_id = request.args.get('class_id')
    palier = request.args.get('palier', 'Palier 1')
    tc = teacher_class_filter()
    if tc:
        rooms = scoped_query(ClassRoom).filter_by(id=tc).all()
        selected = scoped_query(ClassRoom).get(tc)
    else:
        rooms = scoped_query(ClassRoom).order_by(ClassRoom.level).all()
        selected = scoped_query(ClassRoom).get(class_id) if class_id else (rooms[0] if rooms else None)
    students = scoped_query(Student).filter_by(class_id=selected.id).order_by(Student.last_name).all() if selected else []
    return render_template('evaluations.html', rooms=rooms, selected=selected,
                           students=students, palier=palier)

@app.route('/evaluations/saisir/<int:student_id>', methods=['GET', 'POST'])
@login_required
def saisir_evaluation(student_id):
    student = scoped_query(Student).get_or_404(student_id)
    palier = request.args.get('palier', request.form.get('palier', 'Palier 1'))
    if request.method == 'POST':
        # Delete existing for this palier
        scoped_query(Evaluation).filter_by(student_id=student_id, palier=palier).delete()
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
    for e in scoped_query(Evaluation).filter_by(student_id=student_id, palier=palier).all():
        existing[f"{e.matiere}_{e.competence}_{e.critere}"] = e.score
    return render_template('saisir_evaluation.html', student=student,
                           palier=palier, existing=existing)

def compute_bulletin_data(student_id, palier):
    """Calcule notes de compétence, maîtrise, etc."""
    evals = scoped_query(Evaluation).filter_by(student_id=student_id, palier=palier).all()
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

@app.route('/bulletins', methods=['GET', 'HEAD'])
@login_required
def bulletins():
    class_id = request.args.get('class_id')
    palier = request.args.get('palier', 'Palier 1')
    tc = teacher_class_filter()
    if tc:
        rooms = scoped_query(ClassRoom).filter_by(id=tc).all()
        selected = scoped_query(ClassRoom).get(tc)
    else:
        rooms = scoped_query(ClassRoom).order_by(ClassRoom.level).all()
        selected = scoped_query(ClassRoom).get(class_id) if class_id else (rooms[0] if rooms else None)
    students = scoped_query(Student).filter_by(class_id=selected.id).order_by(Student.last_name).all() if selected else []
    return render_template('bulletins.html', rooms=rooms, selected=selected,
                           students=students, palier=palier)

@app.route('/bulletins/<int:student_id>')
@login_required
def bulletin(student_id):
    student = scoped_query(Student).get_or_404(student_id)
    tc = teacher_class_filter()
    if tc and student.class_id != tc:
        flash('Accès réservé aux élèves de votre classe.', 'danger')
        return redirect(url_for('bulletins'))
    palier = request.args.get('palier', 'Palier 1')
    data, palier_mastery = compute_bulletin_data(student_id, palier)
    settings = scoped_query(SchoolSettings).first()
    return render_template('bulletin_detail.html', student=student, palier=palier,
                           data=data, palier_mastery=palier_mastery, settings=settings)

@app.route('/bulletins/<int:student_id>/pdf', methods=['GET', 'HEAD'])
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

    student = scoped_query(Student).get_or_404(student_id)
    # Accès école OU parent authentifié pour CET élève
    parent_ok = session.get('parent_ok') and session.get('parent_student_id') == student_id
    if not session.get('user_id') and not parent_ok:
        return redirect(url_for('login'))
    if session.get('user_id'):
        tc = teacher_class_filter()
        if tc and student.class_id != tc:
            flash('Accès réservé aux élèves de votre classe.', 'danger')
            return redirect(url_for('bulletins'))

    settings = scoped_query(SchoolSettings).first()
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
    students = scoped_query(Student).filter_by(class_id=class_id).order_by(Student.last_name).all()
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


@app.route('/releves', methods=['GET', 'HEAD'])
@login_required
def releves():
    """Liste des relevés de notes par classe + rapports automatiques"""
    class_id = request.args.get('class_id')
    palier = request.args.get('palier', 'Palier 1')
    tc = teacher_class_filter()
    if tc:
        rooms = scoped_query(ClassRoom).filter_by(id=tc).all()
        selected = scoped_query(ClassRoom).get(tc)
    else:
        rooms = scoped_query(ClassRoom).order_by(ClassRoom.level).all()
        selected = scoped_query(ClassRoom).get(class_id) if class_id else (rooms[0] if rooms else None)
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
    room = scoped_query(ClassRoom).get_or_404(class_id)
    report = compute_palier_report(class_id, palier)
    recap = compute_recap_reussite(class_id)
    settings = scoped_query(SchoolSettings).first()

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

@app.route('/cartes', methods=['GET', 'HEAD'])
@login_required
def cartes():
    classes = scoped_query(ClassRoom).order_by(ClassRoom.level).all()
    return render_template('cartes.html', classes=classes)

@app.route('/cartes/classe/<int:id>', methods=['GET', 'HEAD'])
@login_required
def cartes_classe(id):
    room = scoped_query(ClassRoom).filter_by(id=id).first()
    if not room:
        flash('Classe introuvable.', 'danger')
        return redirect(url_for('cartes'))
    tc = teacher_class_filter()
    if tc and tc != id:
        flash('Accès réservé à votre classe.', 'danger')
        return redirect(url_for('cartes'))
    students = scoped_query(Student).filter_by(class_id=id).order_by(Student.last_name, Student.first_name).all()
    settings = scoped_query(SchoolSettings).first()
    return render_template('cartes_classe.html', room=room, students=students, settings=settings)

@app.route('/cartes/eleve/<int:id>', methods=['GET', 'HEAD'])
@login_required
def carte_eleve(id):
    student = scoped_query(Student).filter_by(id=id).first()
    if not student:
        flash('Élève introuvable.', 'danger')
        return redirect(url_for('cartes'))
    tc = teacher_class_filter()
    if tc and student.class_id != tc:
        flash('Accès réservé à votre classe.', 'danger')
        return redirect(url_for('cartes'))
    settings = scoped_query(SchoolSettings).first()
    return render_template('carte_eleve.html', student=student, settings=settings)

# ==================== PARAMÈTRES ====================

@app.route('/parametres', methods=['GET', 'POST'])
@director_required
def parametres():
    settings = scoped_query(SchoolSettings).first()
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
        settings.smtp_enabled = request.form.get('smtp_enabled') == 'on'
        settings.smtp_host = request.form.get('smtp_host', 'smtp.gmail.com')
        try:
            settings.smtp_port = int(request.form.get('smtp_port') or 587)
        except ValueError:
            settings.smtp_port = 587
        settings.smtp_user = request.form.get('smtp_user', '')
        pwd = request.form.get('smtp_password', '')
        if pwd:  # ne pas écraser si champ vide
            settings.smtp_password = pwd
        settings.smtp_from = request.form.get('smtp_from', '')
        settings.smtp_use_tls = request.form.get('smtp_use_tls') == 'on'
        settings.logo_path = request.form.get('logo_path', settings.logo_path or '')
        settings.logo2_path = request.form.get('logo_path2', settings.logo2_path or '')
        settings.logo3_path = request.form.get('logo_path3', settings.logo3_path or '')
        settings.logo4_path = request.form.get('logo_path4', settings.logo4_path or '')

        db.session.commit()
        flash('Paramètres mis à jour.', 'success')
        return redirect(url_for('parametres'))
    return render_template('parametres.html', settings=settings)


# ==================== RÉINSCRIPTION / PASSAGE DE CLASSE ====================

NEXT_LEVEL = {
    'PS': 'MS',
    'MS': 'GS',
    'GS': '1ère année',
    '1ère année': '2ème année',
    '2ème année': '3ème année',
    '3ème année': '4ème année',
    '4ème année': '5ème année',
    '5ème année': 'CEP',
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
    settings = scoped_query(SchoolSettings).first()
    students = scoped_query(Student).order_by(Student.last_name).all()
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
    settings = scoped_query(SchoolSettings).first()
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
        s = scoped_query(Student).get(int(sid))
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
            next_class = scoped_query(ClassRoom).filter_by(level=next_lv).first()
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
        student = scoped_query(Student).filter(
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
    classes = scoped_query(ClassRoom).order_by(ClassRoom.level).all()
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
        password_plain=password,
        full_name=full_name,
        role='Enseignant',
        is_creator=False,
        tenant_id=current_tenant_id(),
        class_id=int(class_id) if class_id else None
    )
    db.session.add(u)
    # Mettre à jour le nom de l'enseignant sur la classe
    if class_id:
        room = scoped_query(ClassRoom).get(int(class_id))
        if room:
            room.teacher = full_name
    db.session.commit()
    flash(f'Enseignant {full_name} créé. Identifiant : {username}', 'success')
    return redirect(url_for('enseignants'))

@app.route('/enseignants/<int:id>/supprimer', methods=['GET', 'POST'])
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
    inbox = scoped_query(Message).filter_by(to_user_id=uid).order_by(Message.created_at.desc()).all()
    sent = scoped_query(Message).filter_by(from_user_id=uid).order_by(Message.created_at.desc()).all()
    # Destinataires possibles
    if session.get('role') == 'Directeur':
        contacts = User.query.filter_by(role='Enseignant').order_by(User.full_name).all()
    else:
        contacts = User.query.filter_by(role='Directeur').order_by(User.full_name).all()
    unread = scoped_query(Message).filter_by(to_user_id=uid, is_read=False).count()
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
    msg = scoped_query(Message).get_or_404(id)
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
        classes = scoped_query(ClassRoom).filter_by(id=tc).all()
        students = scoped_query(Student).filter_by(class_id=tc).order_by(Student.last_name).all()
    else:
        classes = scoped_query(ClassRoom).order_by(ClassRoom.level, ClassRoom.name).all()
        students = scoped_query(Student).order_by(Student.last_name).all()
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
        s = scoped_query(Student).get(int(student_id))
        if s and (not tc or s.class_id == tc):
            targets = [s]
    elif mode == 'class' and class_id:
        cid = int(class_id)
        if tc and tc != cid:
            flash('Accès réservé à votre classe.', 'danger')
            return redirect(url_for('whatsapp'))
        targets = scoped_query(Student).filter_by(class_id=cid).order_by(Student.last_name).all()
    elif mode == 'school':
        if session.get('role') not in ('Directeur', 'Createur') and not session.get('is_creator'):
            flash('Seul le directeur peut écrire à toute l\'école.', 'danger')
            return redirect(url_for('whatsapp'))
        targets = scoped_query(Student).order_by(Student.last_name).all()
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
    settings = scoped_query(SchoolSettings).first()
    tc = teacher_class_filter()
    if tc:
        classes = scoped_query(ClassRoom).filter_by(id=tc).all()
        students = scoped_query(Student).filter_by(class_id=tc).order_by(Student.last_name).all()
    else:
        classes = scoped_query(ClassRoom).order_by(ClassRoom.level, ClassRoom.name).all()
        students = scoped_query(Student).order_by(Student.last_name).all()
    logs = scoped_query(SmsLog).order_by(SmsLog.created_at.desc()).limit(50).all()
    return render_template('sms.html', classes=classes, students=students,
                           settings=settings, logs=logs)

@app.route('/sms/envoyer', methods=['POST'])
@login_required
def sms_envoyer():
    settings = scoped_query(SchoolSettings).first()
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
        s = scoped_query(Student).get(int(student_id))
        if s and (not tc or s.class_id == tc):
            targets = [s]
    elif mode == 'class' and class_id:
        cid = int(class_id)
        if tc and tc != cid:
            flash('Accès réservé à votre classe.', 'danger')
            return redirect(url_for('sms_notifications'))
        targets = scoped_query(Student).filter_by(class_id=cid).all()
    elif mode == 'school':
        if session.get('role') != 'Directeur':
            flash('Seul le directeur peut écrire à toute l\'école.', 'danger')
            return redirect(url_for('sms_notifications'))
        targets = scoped_query(Student).all()
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

@app.route('/appels', methods=['GET', 'POST', 'HEAD'])
@app.route('/appels/', methods=['GET', 'POST', 'HEAD'])
@login_required
def appels():
    tc = teacher_class_filter()
    if tc:
        rooms = scoped_query(ClassRoom).filter_by(id=tc).all()
    else:
        rooms = scoped_query(ClassRoom).order_by(ClassRoom.level, ClassRoom.name).all()
    class_id = request.args.get('class_id', type=int) or (tc or (rooms[0].id if rooms else None))
    date_str = request.args.get('date', date.today().isoformat())
    try:
        selected = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        selected = date.today()
    hol, hol_label = is_holiday(selected)
    weekend = selected.weekday() >= 5
    students = scoped_query(Student).filter_by(class_id=class_id).order_by(Student.last_name).all() if class_id else []
    atts = {}
    if class_id:
        for a in scoped_query(Attendance).filter(
            Attendance.date == selected,
            Attendance.student_id.in_([s.id for s in students] or [0])
        ).all():
            atts[a.student_id] = a
    room = scoped_query(ClassRoom).get(class_id) if class_id else None
    freq = compute_frequentation(class_id) if class_id else None
    return render_template('appels.html', rooms=rooms, room=room, students=students,
                           selected=selected, atts=atts, is_holiday=hol, holiday_label=hol_label,
                           is_weekend=weekend, freq=freq)

@app.route('/appels/marquer', methods=['GET', 'POST'])
@login_required
def appels_marquer():
    if request.method == 'GET':
        return redirect(url_for('appels'))
    student_id = int(request.form.get('student_id'))
    date_str = request.form.get('date')
    status = request.form.get('status', 'Présent')
    selected = datetime.strptime(date_str, '%Y-%m-%d').date()
    student = scoped_query(Student).get_or_404(student_id)
    tc = teacher_class_filter()
    if tc and student.class_id != tc:
        flash('Accès réservé à votre classe.', 'danger')
        return redirect(url_for('appels'))
    if not is_school_day(selected):
        flash("Ce jour n'est pas un jour de classe (week-end ou ferie).", "warning")
        return redirect(url_for('appels', class_id=student.class_id, date=date_str))
    att = scoped_query(Attendance).filter_by(student_id=student_id, date=selected).first()
    if att:
        att.status = status
    else:
        db.session.add(Attendance(student_id=student_id, date=selected, status=status))
    db.session.commit()
    return redirect(url_for('appels', class_id=student.class_id, date=date_str))

@app.route('/appels/marquer-tous', methods=['GET', 'POST'])
@login_required
def appels_marquer_tous():
    if request.method == 'GET':
        return redirect(url_for('appels'))
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
    students = scoped_query(Student).filter_by(class_id=class_id).all()
    for s in students:
        att = scoped_query(Attendance).filter_by(student_id=s.id, date=selected).first()
        if att:
            att.status = status
        else:
            db.session.add(Attendance(student_id=s.id, date=selected, status=status))
    db.session.commit()
    flash(f'Tous marqués : {status}', 'success')
    return redirect(url_for('appels', class_id=class_id, date=date_str))

@app.route('/appels/stats', methods=['GET', 'HEAD'])
@login_required
def appels_stats():
    tc = teacher_class_filter()
    if tc:
        rooms = scoped_query(ClassRoom).filter_by(id=tc).all()
    else:
        rooms = scoped_query(ClassRoom).order_by(ClassRoom.level).all()
    class_id = request.args.get('class_id', type=int) or (tc or (rooms[0].id if rooms else None))
    start_s = request.args.get('start', (date.today().replace(day=1)).isoformat())
    end_s = request.args.get('end', date.today().isoformat())
    start = datetime.strptime(start_s, '%Y-%m-%d').date()
    end = datetime.strptime(end_s, '%Y-%m-%d').date()
    stats = attendance_stats(class_id, start, end) if class_id else None
    room = scoped_query(ClassRoom).get(class_id) if class_id else None
    freq = compute_frequentation(class_id) if class_id else None
    return render_template('appels_stats.html', rooms=rooms, room=room, stats=stats,
                           start=start, end=end, freq=freq)

@app.route('/appels/recap', methods=['GET', 'HEAD'])
@director_required
def appels_recap():
    """Tableau récapitulatif directeur — toutes les classes"""
    start_s = request.args.get('start', (date.today().replace(day=1)).isoformat())
    end_s = request.args.get('end', date.today().isoformat())
    start = datetime.strptime(start_s, '%Y-%m-%d').date()
    end = datetime.strptime(end_s, '%Y-%m-%d').date()
    rooms = scoped_query(ClassRoom).order_by(ClassRoom.level, ClassRoom.name).all()
    recap = []
    for r in rooms:
        st = attendance_stats(r.id, start, end)
        recap.append({'room': r, 'stats': st})
    return render_template('appels_recap.html', recap=recap, start=start, end=end)

@app.route('/appels/pdf', methods=['GET', 'HEAD'])
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
    room = scoped_query(ClassRoom).get_or_404(class_id)
    stats = attendance_stats(class_id, start, end)
    settings = scoped_query(SchoolSettings).first()

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
            if not scoped_query(Holiday).filter_by(date=dd).first():
                db.session.add(Holiday(date=dd, label=label))
                db.session.commit()
                flash('Jour férié ajouté.', 'success')
        return redirect(url_for('jours_feries'))
    holidays = scoped_query(Holiday).order_by(Holiday.date.desc()).all()
    return render_template('jours_feries.html', holidays=holidays,
                           fixed=GABON_FIXED_HOLIDAYS)

@app.route('/jours-feries/<int:id>/supprimer', methods=['GET', 'POST'])
@director_required
def supprimer_ferie(id):
    h = scoped_query(Holiday).get_or_404(id)
    db.session.delete(h)
    db.session.commit()
    flash('Jour férié supprimé.', 'success')
    return redirect(url_for('jours_feries'))

# ==================== CAHIER JOURNAL ====================

@app.route('/cahier-journal', methods=['GET', 'POST', 'HEAD'])
@app.route('/cahier-journal/', methods=['GET', 'POST', 'HEAD'])
@login_required
def cahier_journal():
    tc = teacher_class_filter()
    if tc:
        rooms = scoped_query(ClassRoom).filter_by(id=tc).all()
    else:
        rooms = scoped_query(ClassRoom).order_by(ClassRoom.level).all()
    class_id = request.args.get('class_id', type=int) or (tc or (rooms[0].id if rooms else None))
    room = scoped_query(ClassRoom).get(class_id) if class_id else None
    entries = []
    if class_id:
        entries = scoped_query(ClassJournal).filter_by(class_id=class_id).order_by(
            ClassJournal.date.desc(), ClassJournal.id.desc()).limit(60).all()
    return render_template('cahier_journal.html', rooms=rooms, room=room, entries=entries, today=date.today().isoformat())

@app.route('/cahier-journal/ajouter', methods=['GET', 'POST'])
@login_required
def cahier_ajouter():
    if request.method == 'GET':
        return redirect(url_for('cahier_journal'))
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

@app.route('/cahier-journal/<int:id>/supprimer', methods=['GET', 'POST'])
@login_required
def cahier_supprimer(id):
    entry = scoped_query(ClassJournal).get_or_404(id)
    tc = teacher_class_filter()
    if tc and entry.class_id != tc:
        flash('Accès refusé.', 'danger')
        return redirect(url_for('cahier_journal'))
    cid = entry.class_id
    db.session.delete(entry)
    db.session.commit()
    flash('Entrée supprimée.', 'success')
    return redirect(url_for('cahier_journal', class_id=cid))

@app.route('/cahier-journal/pdf', methods=['GET', 'HEAD'])
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
    room = scoped_query(ClassRoom).get_or_404(class_id)
    entries = scoped_query(ClassJournal).filter_by(class_id=class_id).order_by(ClassJournal.date.desc()).limit(40).all()
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
    room = scoped_query(ClassRoom).get_or_404(class_id)
    students = scoped_query(Student).filter_by(class_id=class_id).order_by(Student.last_name).all()
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



@app.route('/parametres/test-email', methods=['POST'])
@login_required
def test_smtp():
    if session.get('role') != 'Directeur':
        flash('Accès réservé au directeur.', 'danger')
        return redirect(url_for('dashboard'))
    settings = scoped_query(SchoolSettings).first()
    to = request.form.get('test_email') or (settings.email if settings else '') or session.get('username', '')
    user = User.query.get(session.get('user_id'))
    if user and user.email:
        to = to or user.email
    if not to:
        flash('Indiquez une adresse e-mail de test.', 'danger')
        return redirect(url_for('parametres'))
    ok, msg = send_email(to, 'U nengue — Test SMTP',
                         'Ceci est un message de test. Votre serveur de messagerie fonctionne.', settings)
    flash('E-mail de test envoyé.' if ok else f'Échec : {msg}', 'success' if ok else 'danger')
    return redirect(url_for('parametres'))



# ==================== FICHES PÉDAGOGIQUES ====================

PEDAGO_SUBJECTS = ['Français', 'Mathématiques', 'Éveil']

@app.route('/fiches-pedagogiques')
@login_required
def fiches_pedagogiques():
    rooms = scoped_query(ClassRoom).order_by(ClassRoom.level, ClassRoom.name).all()
    if session.get('role') == 'Enseignant':
        u = User.query.get(session.get('user_id'))
        if u and u.class_id:
            rooms = [r for r in rooms if r.id == u.class_id]
    class_id = request.args.get('class_id', type=int)
    subject = request.args.get('subject', '')
    selected = scoped_query(ClassRoom).get(class_id) if class_id else (rooms[0] if rooms else None)
    q = scoped_query(PedagogicalSheet)
    if selected:
        q = q.filter_by(class_id=selected.id)
    if subject:
        q = q.filter_by(subject=subject)
    sheets = q.order_by(PedagogicalSheet.updated_at.desc()).all()
    return render_template('fiches_pedagogiques.html', rooms=rooms, selected=selected,
                           sheets=sheets, subjects=PEDAGO_SUBJECTS, subject=subject)

@app.route('/fiches-pedagogiques/nouvelle', methods=['GET', 'POST'])
@app.route('/fiches-pedagogiques/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def fiche_pedagogique_form(id=None):
    import json
    sheet = scoped_query(PedagogicalSheet).get(id) if id else None
    rooms = scoped_query(ClassRoom).order_by(ClassRoom.level, ClassRoom.name).all()
    if session.get('role') == 'Enseignant':
        u = User.query.get(session.get('user_id'))
        if u and u.class_id:
            rooms = [r for r in rooms if r.id == u.class_id]
            if sheet and sheet.class_id != u.class_id:
                flash('Accès refusé.', 'danger')
                return redirect(url_for('fiches_pedagogiques'))
    if request.method == 'POST':
        class_id = request.form.get('class_id', type=int)
        if session.get('role') == 'Enseignant':
            u = User.query.get(session.get('user_id'))
            if not u or u.class_id != class_id:
                flash('Accès réservé à votre classe.', 'danger')
                return redirect(url_for('fiches_pedagogiques'))
        if not sheet:
            sheet = PedagogicalSheet(created_by=session.get('user_id'))
            db.session.add(sheet)
        sheet.class_id = class_id
        sheet.title = request.form.get('title', '').strip()
        sheet.subject = request.form.get('subject', 'Français')
        sheet.sub_discipline = request.form.get('sub_discipline', '').strip()
        sheet.duration = request.form.get('duration', '30 min').strip()
        sheet.domain = request.form.get('domain', '').strip()
        sheet.approach = request.form.get('approach', '').strip()
        sheet.notion = request.form.get('notion', '').strip()
        sheet.material = request.form.get('material', '').strip()
        sheet.objective = request.form.get('objective', '').strip()
        sheet.competence = request.form.get('competence', '').strip()
        sheet.written_trace = request.form.get('written_trace', '').strip()
        sheet.teacher = request.form.get('teacher', '').strip()
        # phases
        phases = []
        names = request.form.getlist('phase_name[]')
        durs = request.form.getlist('phase_duration[]')
        teachers = request.form.getlist('phase_teacher[]')
        students = request.form.getlist('phase_student[]')
        for i in range(len(names)):
            n = (names[i] or '').strip()
            if not n:
                continue
            phases.append({
                'name': n,
                'duration': (durs[i] if i < len(durs) else '').strip(),
                'teacher': (teachers[i] if i < len(teachers) else '').strip(),
                'student': (students[i] if i < len(students) else '').strip(),
            })
        sheet.phases_json = json.dumps(phases, ensure_ascii=False)
        db.session.commit()
        flash('Fiche pédagogique enregistrée.', 'success')
        return redirect(url_for('fiche_pedagogique_detail', id=sheet.id))
    phases = sheet.phases() if sheet else [
        {'name': '1. Ouverture', 'duration': '4 min', 'teacher': '', 'student': ''},
        {'name': '2. Modélisation', 'duration': '7 min', 'teacher': '', 'student': ''},
        {'name': '3. Pratique guidée', 'duration': '7 min', 'teacher': '', 'student': ''},
        {'name': '4. Pratique autonome', 'duration': '9 min', 'teacher': '', 'student': ''},
        {'name': '5. Clôture', 'duration': '3 min', 'teacher': '', 'student': ''},
    ]
    room_levels = {str(r.id): (r.level or '') for r in rooms}
    return render_template('fiche_pedagogique_form.html', sheet=sheet, rooms=rooms,
                           subjects=PEDAGO_SUBJECTS, phases=phases, room_levels=room_levels)

@app.route('/fiches-pedagogiques/<int:id>')
@login_required
def fiche_pedagogique_detail(id):
    sheet = scoped_query(PedagogicalSheet).get_or_404(id)
    if session.get('role') == 'Enseignant':
        u = User.query.get(session.get('user_id'))
        if not u or u.class_id != sheet.class_id:
            flash('Accès refusé.', 'danger')
            return redirect(url_for('fiches_pedagogiques'))
    return render_template('fiche_pedagogique_detail.html', sheet=sheet)

@app.route('/fiches-pedagogiques/<int:id>/supprimer', methods=['POST'])
@login_required
def fiche_pedagogique_delete(id):
    sheet = scoped_query(PedagogicalSheet).get_or_404(id)
    if session.get('role') == 'Enseignant':
        u = User.query.get(session.get('user_id'))
        if not u or u.class_id != sheet.class_id:
            flash('Accès refusé.', 'danger')
            return redirect(url_for('fiches_pedagogiques'))
    cid = sheet.class_id
    db.session.delete(sheet)
    db.session.commit()
    flash('Fiche supprimée.', 'success')
    return redirect(url_for('fiches_pedagogiques', class_id=cid))

@app.route('/fiches-pedagogiques/<int:id>/pdf')
@login_required
def fiche_pedagogique_pdf(id):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, HRFlowable
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT

    sheet = scoped_query(PedagogicalSheet).get_or_404(id)
    if session.get('role') == 'Enseignant':
        u = User.query.get(session.get('user_id'))
        if not u or u.class_id != sheet.class_id:
            flash('Accès refusé.', 'danger')
            return redirect(url_for('fiches_pedagogiques'))
    settings = scoped_query(SchoolSettings).first()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4,
                            leftMargin=1.5*cm, rightMargin=1.5*cm,
                            topMargin=1.2*cm, bottomMargin=1.2*cm)
    styles = getSampleStyleSheet()
    title_s = ParagraphStyle('t', parent=styles['Normal'], fontSize=14, alignment=TA_CENTER,
                             fontName='Helvetica-Bold', textColor=colors.HexColor('#a21caf'), spaceAfter=8)
    h_s = ParagraphStyle('h', parent=styles['Normal'], fontSize=9, fontName='Helvetica-Bold',
                         textColor=colors.HexColor('#86198f'), spaceBefore=6, spaceAfter=3)
    body = ParagraphStyle('b', parent=styles['Normal'], fontSize=8, leading=11)
    cell = ParagraphStyle('c', parent=styles['Normal'], fontSize=7.5, leading=10)

    elements = []
    school = settings.school_name if settings else 'École Primaire'
    elements.append(Paragraph('FICHE PÉDAGOGIQUE', title_s))
    sub = sheet.title or sheet.sub_discipline or sheet.subject
    elements.append(Paragraph(f'{sub.upper()} — {school}', ParagraphStyle(
        's', parent=styles['Normal'], fontSize=10, alignment=TA_CENTER, spaceAfter=8)))

    cls_name = sheet.classroom.name if sheet.classroom else '—'
    header = [
        [Paragraph(f'<b>Classe :</b> {cls_name}', cell),
         Paragraph(f'<b>Durée :</b> {sheet.duration or "—"}', cell),
         Paragraph(f'<b>Domaine :</b> {sheet.domain or sheet.subject}', cell)],
        [Paragraph(f'<b>Démarche :</b> {sheet.approach or "—"}', cell),
         Paragraph(f'<b>Notion :</b> {sheet.notion or "—"}', cell),
         Paragraph(f'<b>Matériel :</b> {sheet.material or "—"}', cell)],
    ]
    ht = Table(header, colWidths=[5.5*cm, 5.5*cm, 5.5*cm])
    ht.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fdf4ff')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#c026d3')),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#e879f9')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
        ('LEFTPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(ht)
    elements.append(Spacer(1, 4*mm))
    elements.append(Paragraph(f'<b>Objectif :</b> {sheet.objective or "—"}', body))
    elements.append(Paragraph(f'<b>Compétence :</b> {sheet.competence or "—"}', body))
    elements.append(Spacer(1, 3*mm))

    phases = sheet.phases()
    if phases:
        rows = [[Paragraph('<b>Phases</b>', cell),
                 Paragraph('<b>Actions de l\'enseignant</b>', cell),
                 Paragraph('<b>Actions des élèves</b>', cell)]]
        for p in phases:
            phase_label = p.get('name', '')
            if p.get('duration'):
                phase_label += f'<br/><font size="6">{p.get("duration")}</font>'
            rows.append([
                Paragraph(phase_label, cell),
                Paragraph(p.get('teacher') or '—', cell),
                Paragraph(p.get('student') or '—', cell),
            ])
        pt = Table(rows, colWidths=[3.2*cm, 7*cm, 6.3*cm])
        pt.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c026d3')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#f5d0fe')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#a21caf')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 4),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
            ('LEFTPADDING', (0, 0), (-1, -1), 3),
        ]))
        elements.append(pt)

    if sheet.written_trace:
        elements.append(Spacer(1, 4*mm))
        elements.append(Paragraph('TRACE ÉCRITE', h_s))
        elements.append(Paragraph(sheet.written_trace, body))

    elements.append(Spacer(1, 6*mm))
    elements.append(Paragraph(
        f'U nengue — {sheet.teacher or ""} — Document généré automatiquement',
        ParagraphStyle('f', parent=styles['Normal'], fontSize=7, alignment=TA_CENTER,
                       textColor=colors.grey)))
    doc.build(elements)
    buffer.seek(0)
    fname = f"fiche_pedago_{sheet.id}.pdf"
    return send_file(buffer, mimetype='application/pdf', as_attachment=True, download_name=fname)




# ==================== EMPLOI DU TEMPS ====================

def _slot_signature(slots):
    """Signature pour fusionner les cases identiques sur plusieurs jours."""
    if not slots:
        return None
    parts = []
    for s in sorted(slots, key=lambda x: (x.group_label or '', x.subject or '')):
        parts.append((
            (s.subject or '').strip(),
            (s.group_label or '').strip(),
            (s.teacher or '').strip(),
            (s.room or '').strip(),
            (s.color or '').strip(),
            (s.notes or '').strip(),
        ))
    return tuple(parts)

def _build_timetable_rows(slots, days=None):
    """Construit les lignes avec cellules fusionnées (colspan) comme un vrai EDT papier."""
    days = days or SCHEDULE_DAYS
    bands = sorted(set((s.start_time, s.end_time) for s in slots),
                   key=lambda x: x[0].replace('h', ':'))
    grid = {}
    for s in slots:
        grid.setdefault((s.day, s.start_time, s.end_time), []).append(s)

    rows = []
    for start, end in bands:
        cells = []
        i = 0
        while i < len(days):
            day = days[i]
            cell_slots = grid.get((day, start, end), [])
            sig = _slot_signature(cell_slots)
            span = 1
            j = i + 1
            while j < len(days) and sig is not None:
                other = grid.get((days[j], start, end), [])
                if _slot_signature(other) != sig:
                    break
                span += 1
                j += 1
            cells.append({
                'day': day,
                'colspan': span,
                'slots': cell_slots,
                'merged': span > 1,
            })
            i += span
        rows.append({
            'start': start,
            'end': end,
            'label': f'{start} – {end}',
            'cells': cells,
        })
    return rows

@app.route('/emploi-du-temps', methods=['GET', 'POST', 'HEAD'])
@app.route('/emploi-du-temps/', methods=['GET', 'POST', 'HEAD'])
@login_required
def emploi_du_temps():
    rooms = scoped_query(ClassRoom).order_by(ClassRoom.level, ClassRoom.name).all()
    if session.get('role') == 'Enseignant':
        u = User.query.get(session.get('user_id'))
        if u and u.class_id:
            rooms = [r for r in rooms if r.id == u.class_id]
    class_id = request.args.get('class_id', type=int)
    selected = None
    slots = []
    rows = []
    if class_id:
        selected = scoped_query(ClassRoom).get(class_id)
    elif rooms:
        selected = rooms[0]
        class_id = selected.id
    if selected:
        if session.get('role') == 'Enseignant':
            u = User.query.get(session.get('user_id'))
            if u and u.class_id and selected.id != u.class_id:
                flash('Accès réservé à votre classe.', 'danger')
                return redirect(url_for('emploi_du_temps'))
        slots = scoped_query(ScheduleSlot).filter_by(class_id=selected.id).order_by(
            ScheduleSlot.start_time, ScheduleSlot.day).all()
        rows = _build_timetable_rows(slots)
    settings = scoped_query(SchoolSettings).first()
    logos = _public_logo_urls(settings)
    return render_template(
        'emploi_du_temps.html',
        rooms=rooms, selected=selected, slots=slots, rows=rows,
        days=SCHEDULE_DAYS,
        subjects=DEFAULT_SCHEDULE_SUBJECTS,
        subject_color=subject_color,
        settings=settings,
        logos=logos,
    )

def _public_logo_urls(settings):
    """Liste d'URLs (static) pour les logos configurés + dossier static/logos."""
    urls = []
    base = os.path.dirname(__file__)
    seen = set()
    if settings:
        for attr in ('logo_path', 'logo2_path', 'logo3_path', 'logo4_path'):
            rel = (getattr(settings, attr, None) or '').strip()
            if not rel:
                continue
            # normalise vers chemin sous static/
            rel2 = rel.replace('\\', '/')
            if rel2.startswith('static/'):
                rel2 = rel2[7:]
            full = os.path.join(base, 'static', rel2)
            if os.path.isfile(full) and full not in seen:
                seen.add(full)
                urls.append(rel2)
    default_dir = os.path.join(base, 'static', 'logos')
    if os.path.isdir(default_dir):
        for name in sorted(os.listdir(default_dir)):
            if name.startswith('.'):
                continue
            if name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp', '.svg')):
                full = os.path.join(default_dir, name)
                if full not in seen:
                    seen.add(full)
                    urls.append('logos/' + name)
    return urls

@app.route('/emploi-du-temps/ajouter', methods=['GET', 'POST'])
@login_required
def ajouter_creneau():
    if request.method == 'GET':
        return redirect(url_for('emploi_du_temps'))
    class_id = request.form.get('class_id', type=int)
    days = request.form.getlist('days')
    if not days:
        d = request.form.get('day', '').strip()
        if d:
            days = [d]
    start = request.form.get('start_time', '').strip().replace(':', 'h')
    end = request.form.get('end_time', '').strip().replace(':', 'h')
    subject = request.form.get('subject', '').strip()
    teacher = request.form.get('teacher', '').strip()
    color = request.form.get('color', '').strip() or subject_color(subject)
    room = request.form.get('room', '').strip()
    group_label = request.form.get('group_label', '').strip()
    notes = request.form.get('notes', '').strip()
    if not all([class_id, days, start, end, subject]):
        flash('Jour(s), horaires et matière sont obligatoires.', 'danger')
        return redirect(url_for('emploi_du_temps', class_id=class_id))
    if session.get('role') == 'Enseignant':
        u = User.query.get(session.get('user_id'))
        if not u or u.class_id != class_id:
            flash('Accès réservé à votre classe.', 'danger')
            return redirect(url_for('emploi_du_temps'))
    count = 0
    for day in days:
        if day not in SCHEDULE_DAYS:
            continue
        slot = ScheduleSlot(
            class_id=class_id, day=day, start_time=start, end_time=end,
            subject=subject, teacher=teacher, color=color, room=room,
            group_label=group_label, notes=notes
        )
        db.session.add(slot)
        count += 1
    db.session.commit()
    flash(f'{count} créneau(x) ajouté(s)' + (' — affiché(s) fusionné(s) sur la semaine.' if count > 1 else '.'), 'success')
    return redirect(url_for('emploi_du_temps', class_id=class_id))

@app.route('/emploi-du-temps/<int:id>/modifier', methods=['GET', 'POST'])
@login_required
def modifier_creneau(id):
    if request.method == 'GET':
        return redirect(url_for('emploi_du_temps'))
    slot = scoped_query(ScheduleSlot).get_or_404(id)
    if session.get('role') == 'Enseignant':
        u = User.query.get(session.get('user_id'))
        if not u or u.class_id != slot.class_id:
            flash('Accès refusé.', 'danger')
            return redirect(url_for('emploi_du_temps'))
    slot.day = request.form.get('day', slot.day)
    slot.start_time = request.form.get('start_time', slot.start_time).replace(':', 'h')
    slot.end_time = request.form.get('end_time', slot.end_time).replace(':', 'h')
    slot.subject = request.form.get('subject', slot.subject).strip()
    slot.teacher = request.form.get('teacher', '').strip()
    slot.color = request.form.get('color', '').strip() or subject_color(slot.subject)
    slot.room = request.form.get('room', '').strip()
    slot.group_label = request.form.get('group_label', '').strip()
    slot.notes = request.form.get('notes', '').strip()
    db.session.commit()
    flash('Créneau modifié.', 'success')
    return redirect(url_for('emploi_du_temps', class_id=slot.class_id))

@app.route('/emploi-du-temps/<int:id>/supprimer', methods=['POST', 'GET'])
@login_required
def supprimer_creneau(id):
    slot = scoped_query(ScheduleSlot).get_or_404(id)
    cid = slot.class_id
    if session.get('role') == 'Enseignant':
        u = User.query.get(session.get('user_id'))
        if not u or u.class_id != cid:
            flash('Accès refusé.', 'danger')
            return redirect(url_for('emploi_du_temps'))
    db.session.delete(slot)
    db.session.commit()
    flash('Créneau supprimé.', 'success')
    return redirect(url_for('emploi_du_temps', class_id=cid))

@app.route('/emploi-du-temps/<int:class_id>/vider', methods=['GET', 'POST'])
@login_required
def vider_emploi(class_id):
    if session.get('role') == 'Enseignant':
        u = User.query.get(session.get('user_id'))
        if not u or u.class_id != class_id:
            flash('Accès refusé.', 'danger')
            return redirect(url_for('emploi_du_temps'))
    scoped_query(ScheduleSlot).filter_by(class_id=class_id).delete()
    db.session.commit()
    flash('Emploi du temps vidé.', 'success')
    return redirect(url_for('emploi_du_temps', class_id=class_id))

@app.route('/parametres/logos', methods=['POST'])
@login_required
def upload_logos():
    """Téléversement des logos (jusqu'à 4 fichiers)."""
    if session.get('role') != 'Directeur':
        flash('Accès réservé au directeur.', 'danger')
        return redirect(url_for('dashboard'))
    settings = scoped_query(SchoolSettings).first()
    if not settings:
        settings = SchoolSettings()
        db.session.add(settings)
        db.session.commit()
    folder = os.path.join(app.config['UPLOAD_FOLDER'], 'logos')
    os.makedirs(folder, exist_ok=True)
    attrs = ['logo_path', 'logo2_path', 'logo3_path', 'logo4_path']
    fields = ['logo1', 'logo2', 'logo3', 'logo4']
    saved = 0
    for field, attr in zip(fields, attrs):
        f = request.files.get(field)
        if not f or not f.filename:
            continue
        fname = secure_filename(f.filename)
        if not fname:
            continue
        ext = fname.rsplit('.', 1)[-1].lower() if '.' in fname else ''
        if ext not in ('png', 'jpg', 'jpeg', 'gif', 'webp'):
            continue
        dest_name = f'{attr}_{fname}'
        dest = os.path.join(folder, dest_name)
        f.save(dest)
        rel = f'static/uploads/logos/{dest_name}'
        setattr(settings, attr, rel)
        # also copy to static/logos for easy serving
        logos_dir = os.path.join(os.path.dirname(__file__), 'static', 'logos')
        os.makedirs(logos_dir, exist_ok=True)
        try:
            import shutil
            shutil.copy2(dest, os.path.join(logos_dir, dest_name))
        except Exception:
            pass
        saved += 1
    db.session.commit()
    flash(f'{saved} logo(s) enregistré(s).' if saved else 'Aucun fichier valide (png/jpg).', 'success' if saved else 'warning')
    return redirect(url_for('parametres'))

def _schedule_logo_paths(settings):
    paths = []
    base = os.path.dirname(__file__)
    if settings:
        for attr in ('logo_path', 'logo2_path', 'logo3_path', 'logo4_path'):
            rel = (getattr(settings, attr, None) or '').strip()
            if not rel:
                continue
            candidates = [
                rel if os.path.isabs(rel) else os.path.join(base, rel),
                os.path.join(base, 'static', rel.replace('static/', '').lstrip('/')),
            ]
            for full in candidates:
                if os.path.isfile(full):
                    paths.append(full)
                    break
    default_dir = os.path.join(base, 'static', 'logos')
    if os.path.isdir(default_dir):
        for name in sorted(os.listdir(default_dir)):
            if name.startswith('.'):
                continue
            if name.lower().endswith(('.png', '.jpg', '.jpeg', '.gif', '.webp')):
                p = os.path.join(default_dir, name)
                if p not in paths:
                    paths.append(p)
    return paths[:6]

@app.route('/emploi-du-temps/<int:class_id>/pdf', methods=['GET', 'HEAD'])
@login_required
def emploi_pdf(class_id):
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, Image
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.lib.enums import TA_CENTER

    room = scoped_query(ClassRoom).get_or_404(class_id)
    if session.get('role') == 'Enseignant':
        u = User.query.get(session.get('user_id'))
        if not u or u.class_id != class_id:
            flash('Accès refusé.', 'danger')
            return redirect(url_for('emploi_du_temps'))
    settings = scoped_query(SchoolSettings).first()
    slots = scoped_query(ScheduleSlot).filter_by(class_id=class_id).all()
    rows_data = _build_timetable_rows(slots)

    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            leftMargin=0.8*cm, rightMargin=0.8*cm,
                            topMargin=0.6*cm, bottomMargin=0.6*cm)
    styles = getSampleStyleSheet()
    title_style = ParagraphStyle('t', parent=styles['Normal'], fontSize=13,
                                 alignment=TA_CENTER, fontName='Helvetica-Bold',
                                 textColor=colors.HexColor('#a21caf'), spaceAfter=2)
    sub_style = ParagraphStyle('s', parent=styles['Normal'], fontSize=8,
                               alignment=TA_CENTER, spaceAfter=5)
    cell_style = ParagraphStyle('c', parent=styles['Normal'], fontSize=6.5,
                                alignment=TA_CENTER, leading=8)
    small = ParagraphStyle('sm', parent=styles['Normal'], fontSize=6, alignment=TA_CENTER)

    elements = []
    logo_paths = _schedule_logo_paths(settings)
    if logo_paths:
        imgs = []
        for lp in logo_paths:
            try:
                imgs.append(Image(lp, width=2.4*cm, height=2.0*cm, kind='proportional'))
            except Exception:
                pass
        if imgs:
            n = len(imgs)
            logo_table = Table([imgs], colWidths=[26*cm / n] * n)
            logo_table.setStyle(TableStyle([
                ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
                ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ]))
            elements.append(logo_table)
            elements.append(Spacer(1, 2*mm))
    else:
        # Bandeau texte type officiel si aucun logo fichier
        school = (settings.school_name if settings else 'École Primaire')
        banner = Table([[
            Paragraph(f'<b>{school}</b><br/><font size="6">République Gabonaise</font>', small),
            Paragraph('<b>HOMOLOGATION</b><br/><font size="6">Ministère de l\'Éducation</font>', small),
            Paragraph('<b>AEFE</b><br/><font size="6">Enseignement français</font>', small),
            Paragraph('<b>DIRECTION</b><br/><font size="6">Circonscription</font>', small),
        ]], colWidths=[6.5*cm]*4)
        banner.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fdf4ff')),
            ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor('#c026d3')),
            ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#e879f9')),
            ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
            ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(banner)
        elements.append(Spacer(1, 2*mm))

    school = settings.school_name if settings else 'École Primaire'
    annee = settings.annee_scolaire if settings else ''
    elements.append(Paragraph('U nengue — Emploi du temps', title_style))
    elements.append(Paragraph(
        f'{school} — {room.name} ({room.level}) — {annee} — Enseignant(e) : {room.teacher or "—"}',
        sub_style))

    # Table with colspan support via nested content spanning visual cells
    # ReportLab Table doesn't support colspan easily in platypus the same way —
    # build one row of 6 columns; for merged days put text in first and SPAN
    header = ['Horaires'] + SCHEDULE_DAYS
    data = [header]
    span_cmds = []
    for ri, row in enumerate(rows_data, start=1):
        line = [Paragraph(f'<b>{row["start"]}<br/>{row["end"]}</b>', cell_style)]
        # expand to 5 day columns
        day_cells = [''] * 5
        col = 0
        for cell in row['cells']:
            parts = []
            for s in cell['slots']:
                bit = f'<b>{s.subject}</b>'
                if s.group_label:
                    bit = f'<b>{s.group_label}:</b> {bit}'
                if s.teacher:
                    bit += f'<br/><font size="5.5">{s.teacher}</font>'
                if s.room:
                    bit += f'<br/><font size="5">{s.room}</font>'
                parts.append(bit)
            txt = Paragraph('<br/>'.join(parts) if parts else '', cell_style)
            day_cells[col] = txt
            if cell['colspan'] > 1:
                # SPAN (start_col, row) to (end_col, row) — +1 because col 0 is horaires
                c0 = col + 1
                c1 = col + cell['colspan']
                span_cmds.append(('SPAN', (c0, ri), (c1, ri)))
            col += cell['colspan']
        data.append(line + day_cells)

    col_w = [2.4*cm] + [4.6*cm] * 5
    t = Table(data, colWidths=col_w, repeatRows=1)
    style_cmds = [
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('FONTSIZE', (0, 0), (-1, -1), 7),
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c026d3')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('BACKGROUND', (0, 1), (0, -1), colors.HexColor('#f5d0fe')),
        ('ALIGN', (0, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#a21caf')),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ] + span_cmds

    for ri, row in enumerate(rows_data, start=1):
        col = 0
        for cell in row['cells']:
            if cell['slots'] and len(cell['slots']) == 1 and cell['slots'][0].color:
                try:
                    c0 = col + 1
                    c1 = col + cell['colspan']
                    style_cmds.append(('BACKGROUND', (c0, ri), (c1, ri),
                                       colors.HexColor(cell['slots'][0].color)))
                    style_cmds.append(('TEXTCOLOR', (c0, ri), (c1, ri), colors.white))
                except Exception:
                    pass
            elif cell['merged'] and cell['slots']:
                try:
                    c0 = col + 1
                    c1 = col + cell['colspan']
                    style_cmds.append(('BACKGROUND', (c0, ri), (c1, ri),
                                       colors.HexColor('#ddd6fe')))
                except Exception:
                    pass
            col += cell['colspan']

    t.setStyle(TableStyle(style_cmds))
    elements.append(t)
    elements.append(Spacer(1, 5*mm))
    elements.append(Paragraph(
        'Document généré par U nengue — Na buranghe ô dji icole di Gabu — MM',
        ParagraphStyle('f', parent=styles['Normal'], fontSize=7, alignment=TA_CENTER,
                       textColor=colors.grey)))
    doc.build(elements)
    buffer.seek(0)
    fname = f"emploi_{room.name.replace(' ', '_')}.pdf"
    return send_file(buffer, mimetype='application/pdf', as_attachment=True,
                     download_name=fname)


# ==================== RESSOURCES PÉDAGOGIQUES ====================

def _load_dictionary():
    """Charge la banque FR↔EN (~2000 mots) depuis data/dictionnaire_fr_en.json."""
    import json
    path = os.path.join(_BASE_DIR, 'data', 'dictionnaire_fr_en.json')
    try:
        with open(path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        out = []
        for item in data:
            if isinstance(item, (list, tuple)) and len(item) >= 2:
                out.append((str(item[0]), str(item[1])))
            elif isinstance(item, dict) and item.get('fr') and item.get('en'):
                out.append((str(item['fr']), str(item['en'])))
        if out:
            return out
    except Exception:
        pass
    return [
        ('école', 'school'), ('élève', 'pupil'), ('livre', 'book'),
        ('bonjour', 'hello'), ('merci', 'thank you'),
    ]


DICTIONARY_WORDS = _load_dictionary()

def _load_ipunu_dict():
    import json
    p = os.path.join(_BASE_DIR, 'data', 'dictionnaire_ipunu.json')
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

def _load_ipunu_lecons():
    import json
    p = os.path.join(_BASE_DIR, 'data', 'lecons_ipunu.json')
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

IPUNU_DICT = _load_ipunu_dict()
IPUNU_LECONS = _load_ipunu_lecons()

def _load_ipunu_pron():
    import json
    p = os.path.join(_BASE_DIR, 'data', 'prononciation_ipunu.json')
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {}

IPUNU_PRON = _load_ipunu_pron()

def _load_json_data(name):
    import json
    p = os.path.join(_BASE_DIR, 'data', name)
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return {} if name.startswith('cours') else []

IPUNU_COURS = _load_json_data('cours_ipunu.json')
IPUNU_EXERCICES = _load_json_data('exercices_ipunu.json') or []
IPUNU_EVALS = _load_json_data('evaluations_ipunu.json') or []

def _load_banque_activites():
    import json
    p = os.path.join(_BASE_DIR, 'data', 'banque_activites.json')
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

BANQUE_ACTIVITES = _load_banque_activites()


def _load_hebreu_dict():
    import json
    p = os.path.join(_BASE_DIR, 'data', 'dictionnaire_hebreu.json')
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

def _load_hebreu_lecons():
    import json
    p = os.path.join(_BASE_DIR, 'data', 'lecons_hebreu.json')
    try:
        with open(p, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception:
        return []

HEBREU_DICT = _load_hebreu_dict()
HEBREU_LECONS = _load_hebreu_lecons()



# Programmes officiels structurés (Cycle 1-3 / mapping Gabon PS→5ème)
# Sources : programmes FR cycle 1, 2, 3 (français, maths, EMC, etc.) adaptés aux niveaux U nengue

# PDF officiels (vos documents) servis depuis static/programmes/
PROGRAMME_PDFS = {
    'PS': [
        {'titre': 'Programme maternelle (cycle 1)', 'fichier': 'cycle1-maternelle.pdf', 'type': 'programme', 'matiere': 'Général'},
        {'titre': 'Annexe programme maternelle', 'fichier': 'cycle1-annexe-maternelle.pdf', 'type': 'programme', 'matiere': 'Général'},
        {'titre': 'Livret langage oral et écrit — avant 4 ans', 'fichier': 'livret-langage-avant4ans.pdf', 'type': 'livret', 'matiere': 'Français'},
        {'titre': 'Français cycle 1', 'fichier': 'cycle1-francais.pdf', 'type': 'programme', 'matiere': 'Français'},
        {'titre': 'Mathématiques cycle 1', 'fichier': 'cycle1-maths.pdf', 'type': 'programme', 'matiere': 'Mathématiques'},
    ],
    'MS': [
        {'titre': 'Programme maternelle (cycle 1)', 'fichier': 'cycle1-maternelle.pdf', 'type': 'programme', 'matiere': 'Général'},
        {'titre': 'Annexe programme maternelle', 'fichier': 'cycle1-annexe-maternelle.pdf', 'type': 'programme', 'matiere': 'Général'},
        {'titre': 'Livret langage — à partir de 4 ans', 'fichier': 'livret-langage-avant4ans.pdf', 'type': 'livret', 'matiere': 'Français'},
        {'titre': 'Livret maths — à partir de 4 ans', 'fichier': 'livret-maths-apartir4ans.pdf', 'type': 'livret', 'matiere': 'Mathématiques'},
        {'titre': 'Français cycle 1', 'fichier': 'cycle1-francais.pdf', 'type': 'programme', 'matiere': 'Français'},
        {'titre': 'Mathématiques cycle 1', 'fichier': 'cycle1-maths.pdf', 'type': 'programme', 'matiere': 'Mathématiques'},
    ],
    'GS': [
        {'titre': 'Programme maternelle (cycle 1)', 'fichier': 'cycle1-maternelle.pdf', 'type': 'programme', 'matiere': 'Général'},
        {'titre': 'Annexe programme maternelle', 'fichier': 'cycle1-annexe-maternelle.pdf', 'type': 'programme', 'matiere': 'Général'},
        {'titre': 'Livret langage — à partir de 5 ans', 'fichier': 'livret-langage-apartir5ans.pdf', 'type': 'livret', 'matiere': 'Français'},
        {'titre': 'Livret maths — à partir de 5 ans', 'fichier': 'livret-maths-apartir5ans.pdf', 'type': 'livret', 'matiere': 'Mathématiques'},
        {'titre': 'Français cycle 1', 'fichier': 'cycle1-francais.pdf', 'type': 'programme', 'matiere': 'Français'},
        {'titre': 'Mathématiques cycle 1', 'fichier': 'cycle1-maths.pdf', 'type': 'programme', 'matiere': 'Mathématiques'},
    ],
    '1ère année': [
        {'titre': 'Livret d\'accompagnement Français CP', 'fichier': 'livret-francais-cp.pdf', 'type': 'livret', 'matiere': 'Français'},
        {'titre': 'Guide lecture et écriture au CP', 'fichier': 'guide-lecture-ecriture-cp.pdf', 'type': 'guide', 'matiere': 'Français'},
        {'titre': 'Guide grammaire CP à 6e', 'fichier': 'guide-grammaire-cp-6e.pdf', 'type': 'guide', 'matiere': 'Français'},
        {'titre': 'Terminologie grammaticale', 'fichier': 'guide-grammaire-terminologie.pdf', 'type': 'guide', 'matiere': 'Français'},
        {'titre': 'Français cycle 2 (programme)', 'fichier': 'cycle2-francais.pdf', 'type': 'programme', 'matiere': 'Français'},
        {'titre': 'Français cycle 2 (tableau)', 'fichier': 'cycle2-francais-tableau.pdf', 'type': 'tableau', 'matiere': 'Français'},
        {'titre': 'Guide nombres, calcul, problèmes CP', 'fichier': 'guide-maths-nombres-cp.pdf', 'type': 'guide', 'matiere': 'Mathématiques'},
        {'titre': 'Guide calcul mental CP–CM2', 'fichier': 'guide-calcul-mental-cp-cm2.pdf', 'type': 'guide', 'matiere': 'Mathématiques'},
        {'titre': 'Mathématiques cycle 2 (tableau)', 'fichier': 'cycle2-maths-tableau.pdf', 'type': 'tableau', 'matiere': 'Mathématiques'},
        {'titre': 'Livret EMC CP', 'fichier': 'livret-emc-cp.pdf', 'type': 'livret', 'matiere': 'EMC'},
        {'titre': 'Histoire-géographie cycle 2', 'fichier': 'cycle2-histoire-geo.pdf', 'type': 'programme', 'matiere': 'Histoire-Géo'},
        {'titre': 'EMC (CP → Terminale)', 'fichier': 'emc-cp-terminale.pdf', 'type': 'programme', 'matiere': 'EMC'},
    ],
    '2ème année': [
        {'titre': 'Livret d\'accompagnement Français CE1', 'fichier': 'livret-francais-ce1.pdf', 'type': 'livret', 'matiere': 'Français'},
        {'titre': 'Guide grammaire CP à 6e', 'fichier': 'guide-grammaire-cp-6e.pdf', 'type': 'guide', 'matiere': 'Français'},
        {'titre': 'Terminologie grammaticale', 'fichier': 'guide-grammaire-terminologie.pdf', 'type': 'guide', 'matiere': 'Français'},
        {'titre': 'Français cycle 2 (programme)', 'fichier': 'cycle2-francais.pdf', 'type': 'programme', 'matiere': 'Français'},
        {'titre': 'Français cycle 2 (tableau)', 'fichier': 'cycle2-francais-tableau.pdf', 'type': 'tableau', 'matiere': 'Français'},
        {'titre': 'Livret Mathématiques CE1', 'fichier': 'livret-maths-ce1.pdf', 'type': 'livret', 'matiere': 'Mathématiques'},
        {'titre': 'Guide calcul mental CP–CM2', 'fichier': 'guide-calcul-mental-cp-cm2.pdf', 'type': 'guide', 'matiere': 'Mathématiques'},
        {'titre': 'Mathématiques cycle 2 (tableau)', 'fichier': 'cycle2-maths-tableau.pdf', 'type': 'tableau', 'matiere': 'Mathématiques'},
        {'titre': 'Histoire-géographie cycle 2', 'fichier': 'cycle2-histoire-geo.pdf', 'type': 'programme', 'matiere': 'Histoire-Géo'},
        {'titre': 'EMC (CP → Terminale)', 'fichier': 'emc-cp-terminale.pdf', 'type': 'programme', 'matiere': 'EMC'},
    ],
    '3ème année': [
        {'titre': 'Livret Mathématiques CE2', 'fichier': 'livret-maths-ce2.pdf', 'type': 'livret', 'matiere': 'Mathématiques'},
        {'titre': 'Guide grammaire CP à 6e', 'fichier': 'guide-grammaire-cp-6e.pdf', 'type': 'guide', 'matiere': 'Français'},
        {'titre': 'Terminologie grammaticale', 'fichier': 'guide-grammaire-terminologie.pdf', 'type': 'guide', 'matiere': 'Français'},
        {'titre': 'Français cycle 2 (programme)', 'fichier': 'cycle2-francais.pdf', 'type': 'programme', 'matiere': 'Français'},
        {'titre': 'Français cycle 2 (tableau)', 'fichier': 'cycle2-francais-tableau.pdf', 'type': 'tableau', 'matiere': 'Français'},
        {'titre': 'Guide calcul mental CP–CM2', 'fichier': 'guide-calcul-mental-cp-cm2.pdf', 'type': 'guide', 'matiere': 'Mathématiques'},
        {'titre': 'Mathématiques cycle 2 (tableau)', 'fichier': 'cycle2-maths-tableau.pdf', 'type': 'tableau', 'matiere': 'Mathématiques'},
        {'titre': 'Histoire-géographie cycle 2', 'fichier': 'cycle2-histoire-geo.pdf', 'type': 'programme', 'matiere': 'Histoire-Géo'},
        {'titre': 'EMC (CP → Terminale)', 'fichier': 'emc-cp-terminale.pdf', 'type': 'programme', 'matiere': 'EMC'},
    ],
    '4ème année': [
        {'titre': 'Exemples mise en œuvre Français CM1', 'fichier': 'exemples-francais-cm1.pdf', 'type': 'exemples', 'matiere': 'Français'},
        {'titre': 'Exemples mise en œuvre Maths CM1', 'fichier': 'exemples-maths-cm1.pdf', 'type': 'exemples', 'matiere': 'Mathématiques'},
        {'titre': 'Guide grammaire CP à 6e', 'fichier': 'guide-grammaire-cp-6e.pdf', 'type': 'guide', 'matiere': 'Français'},
        {'titre': 'Terminologie grammaticale', 'fichier': 'guide-grammaire-terminologie.pdf', 'type': 'guide', 'matiere': 'Français'},
        {'titre': 'Programme cycle 3 (complet)', 'fichier': 'cycle3-complet.pdf', 'type': 'programme', 'matiere': 'Général'},
        {'titre': 'Français cycle 3 (tableau)', 'fichier': 'cycle3-francais-tableau.pdf', 'type': 'tableau', 'matiere': 'Français'},
        {'titre': 'Mathématiques cycle 3 (tableau)', 'fichier': 'cycle3-maths-tableau.pdf', 'type': 'tableau', 'matiere': 'Mathématiques'},
        {'titre': 'Guide calcul mental CP–CM2', 'fichier': 'guide-calcul-mental-cp-cm2.pdf', 'type': 'guide', 'matiere': 'Mathématiques'},
        {'titre': 'Histoire-géographie cycle 3', 'fichier': 'cycle3-histoire-geo.pdf', 'type': 'programme', 'matiere': 'Histoire-Géo'},
        {'titre': 'EMC (CP → Terminale)', 'fichier': 'emc-cp-terminale.pdf', 'type': 'programme', 'matiere': 'EMC'},
    ],
    '5ème année': [
        {'titre': 'Exemples mise en œuvre Français CM2', 'fichier': 'exemples-francais-cm2.pdf', 'type': 'exemples', 'matiere': 'Français'},
        {'titre': 'Exemples mise en œuvre Maths CM2', 'fichier': 'exemples-maths-cm2.pdf', 'type': 'exemples', 'matiere': 'Mathématiques'},
        {'titre': 'Guide grammaire CP à 6e', 'fichier': 'guide-grammaire-cp-6e.pdf', 'type': 'guide', 'matiere': 'Français'},
        {'titre': 'Terminologie grammaticale', 'fichier': 'guide-grammaire-terminologie.pdf', 'type': 'guide', 'matiere': 'Français'},
        {'titre': 'Programme cycle 3 (complet)', 'fichier': 'cycle3-complet.pdf', 'type': 'programme', 'matiere': 'Général'},
        {'titre': 'Français cycle 3 (tableau)', 'fichier': 'cycle3-francais-tableau.pdf', 'type': 'tableau', 'matiere': 'Français'},
        {'titre': 'Mathématiques cycle 3 (tableau)', 'fichier': 'cycle3-maths-tableau.pdf', 'type': 'tableau', 'matiere': 'Mathématiques'},
        {'titre': 'Guide calcul mental CP–CM2', 'fichier': 'guide-calcul-mental-cp-cm2.pdf', 'type': 'guide', 'matiere': 'Mathématiques'},
        {'titre': 'Histoire-géographie cycle 3', 'fichier': 'cycle3-histoire-geo.pdf', 'type': 'programme', 'matiere': 'Histoire-Géo'},
        {'titre': 'EMC (CP → Terminale)', 'fichier': 'emc-cp-terminale.pdf', 'type': 'programme', 'matiere': 'EMC'},
    ],
}




PROGRAMMES_OFFICIELS = {
    'PS': {
        'label': 'Petite section (PS)',
        'cycle': 'Cycle 1 — Maternelle',
        'matieres': {
            'Langage oral et écrit': {
                'objectifs': [
                    'Développer le langage oral : écouter, comprendre, s\'exprimer',
                    'Enrichir le vocabulaire du quotidien et des activités de classe',
                    'Découvrir le principe alphabétique (premiers sons, prénom)',
                    'Entrer dans la culture de l\'écrit (albums, comptines, affichages)',
                ],
                'competences': [
                    'Écouter et comprendre un message simple',
                    'S\'exprimer dans un langage compréhensible',
                    'Reconnaître son prénom écrit',
                    'Participer à des échanges guidés',
                ],
                'activites': [
                    'Comptines et jeux de doigts',
                    'Lecture d\'albums par l\'enseignant',
                    'Jeux de langage (qui est-ce ?, devinettes)',
                    'Dictée à l\'adulte (phrases courtes)',
                ],
            },
            'Mathématiques (premiers outils)': {
                'objectifs': [
                    'Découvrir les quantités et les nombres (jusqu\'à 3 puis 5)',
                    'Comparer, trier, classer des objets',
                    'Se repérer dans le temps (journée, rituels)',
                    'Se repérer dans l\'espace proche (classe, cour)',
                ],
                'competences': [
                    'Dénombrer de petites collections',
                    'Associer quantité et symbole (1, 2, 3)',
                    'Ordonner des événements de la journée',
                    'Situer des objets (devant, derrière, sur, sous)',
                ],
                'activites': [
                    'Boîtes à compter et cubes',
                    'Rituels de date et de présence',
                    'Jeux de tri (couleurs, formes, tailles)',
                    'Parcours moteurs et repères spatiaux',
                ],
            },
            'Activités physiques': {
                'objectifs': [
                    'Développer les déplacements et les équilibres',
                    'Coopérer dans des jeux simples',
                    'S\'exprimer avec son corps',
                ],
                'competences': ['Courir, sauter, lancer', 'Respecter des règles de jeu', 'Imiter et danser'],
                'activites': ['Parcours moteurs', 'Jeux de coopération', 'Danses et mimes'],
            },
            'Activités artistiques': {
                'objectifs': [
                    'Dessiner, graphisme libre',
                    'Explorer les sons et la voix',
                    'Éprouver et exprimer des émotions',
                ],
                'competences': ['Tracer, coller, modeler', 'Chanter des comptines', 'Observer des images'],
                'activites': ['Arts plastiques', 'Chansons et instruments', 'Spectacles courts'],
            },
            'Découverte du monde': {
                'objectifs': [
                    'Découvrir le vivant (animaux, végétaux)',
                    'Explorer les objets et matériaux',
                    'Prendre soin de son corps',
                ],
                'competences': ['Observer et nommer', 'Manipuler avec précaution', 'Respecter l\'environnement proche'],
                'activites': ['Jardinage simple', 'Observations en classe', 'Rituels d\'hygiène'],
            },
        },
    },
    'MS': {
        'label': 'Moyenne section (MS)',
        'cycle': 'Cycle 1 — Maternelle',
        'matieres': {
            'Langage oral et écrit': {
                'objectifs': [
                    'Structurer le langage oral (phrases plus complexes)',
                    'Développer la conscience phonologique',
                    'S\'initier à l\'écriture du prénom et de lettres',
                    'Comprendre des histoires plus longues',
                ],
                'competences': [
                    'Raconter un événement vécu',
                    'Distinguer des sons dans les mots',
                    'Reconnaître des lettres familières',
                    'Reformuler une histoire simple',
                ],
                'activites': [
                    'Jeux phonologiques (rimes, syllabes)',
                    'Albums et questionnements',
                    'Écriture du prénom',
                    'Théâtre de marionnettes',
                ],
            },
            'Mathématiques (premiers outils)': {
                'objectifs': [
                    'Nombres jusqu\'à 10 (dénombrement, comparaison)',
                    'Résoudre de petits problèmes concrets',
                    'Se repérer dans le temps (semaine, avant/après)',
                    'Formes géométriques simples',
                ],
                'competences': [
                    'Compter jusqu\'à 10 avec exactitude',
                    'Comparer des quantités (plus, moins, autant)',
                    'Nommer cercle, carré, triangle',
                    'Utiliser le calendrier de la classe',
                ],
                'activites': [
                    'Jeux de dés et cartes',
                    'Situations de partage',
                    'Construction de figures',
                    'Rituels de la date enrichis',
                ],
            },
            'Activités physiques': {
                'objectifs': ['Affiner les gestes moteurs', 'Respecter des règles collectives', 'S\'opposer et coopérer'],
                'competences': ['Enchaîner des actions', 'Jouer en équipe', 'Contrôler son énergie'],
                'activites': ['Jeux collectifs', 'Ateliers d\'équilibre', 'Danses structurées'],
            },
            'Activités artistiques': {
                'objectifs': ['Graphisme dirigé', 'Répertoire de chansons', 'Création plastique'],
                'competences': ['Tracer des formes rythmées', 'Mémoriser des comptines', 'Composer une image'],
                'activites': ['Graphisme', 'Chorale de classe', 'Collages et volumes'],
            },
            'Découverte du monde': {
                'objectifs': ['Cycle de vie simple', 'Matériaux et leurs usages', 'Espace proche élargi'],
                'competences': ['Décrire un animal ou une plante', 'Classer des objets', 'Se situer dans l\'école'],
                'activites': ['Élevage / plantation', 'Expériences simples', 'Promenade exploratoire'],
            },
        },
    },
    'GS': {
        'label': 'Grande section (GS)',
        'cycle': 'Cycle 1 — Maternelle',
        'matieres': {
            'Langage oral et écrit': {
                'objectifs': [
                    'Préparer l\'entrée dans la lecture (principe alphabétique)',
                    'Écrire des mots sous dictée (syllabes connues)',
                    'Comprendre et raconter des textes',
                    'Participer à des échanges structurés',
                ],
                'competences': [
                    'Associer lettres et sons fréquents',
                    'Écrire son prénom et des mots usuels',
                    'Reformuler le fil d\'une histoire',
                    'Prendre la parole devant le groupe',
                ],
                'activites': [
                    'Ateliers phonologie intensifs',
                    'Premiers essais de lecture',
                    'Production d\'écrits courts',
                    'Débats guidés',
                ],
            },
            'Mathématiques (premiers outils)': {
                'objectifs': [
                    'Nombres jusqu\'à 30 (voire au-delà selon les élèves)',
                    'Résolution de problèmes avec manipulation',
                    'Premières écritures additives',
                    'Grandeurs : longueur, contenance',
                ],
                'competences': [
                    'Dénombrer et constituer des collections',
                    'Utiliser le signe + dans des situations',
                    'Comparer des longueurs',
                    'Lire et écrire les nombres jusqu\'à 20/30',
                ],
                'activites': [
                    'Situations-problèmes de la vie de classe',
                    'Jeux de marché',
                    'Frise numérique',
                    'Mesures avec unités non conventionnelles',
                ],
            },
            'Activités physiques': {
                'objectifs': ['Enchaînements moteurs', 'Jeux à règles complexes', 'Expression corporelle'],
                'competences': ['Enchaîner 3 actions', 'Respecter un règlement', 'Créer une petite danse'],
                'activites': ['Parcours évolués', 'Jeux traditionnels', 'Spectacles corporels'],
            },
            'Activités artistiques': {
                'objectifs': ['Graphisme abouti', 'Création intentionnelle', 'Culture artistique'],
                'competences': ['Réaliser une composition', 'Interpréter une chanson', 'Parler d\'une œuvre'],
                'activites': ['Projets artistiques', 'Visite virtuelle d\'œuvres', 'Concerts de classe'],
            },
            'Découverte du monde': {
                'objectifs': ['Vivant et cycles', 'États de la matière', 'Objets techniques simples'],
                'competences': ['Expliquer une observation', 'Tester une hypothèse simple', 'Utiliser un outil adapté'],
                'activites': ['Expériences (eau, glace)', 'Montages simples', 'Carnet d\'observation'],
            },
        },
    },
    '1ère année': {
        'label': '1ère année (équivalent CP)',
        'cycle': 'Cycle 2',
        'matieres': {
            'Français': {
                'objectifs': [
                    'Automatiser le décodage (CGP) — apprentissage systématique et quotidien',
                    'Lire à voix haute des textes courts',
                    'Comprendre un texte simple',
                    'Écrire en cursive, encoder sous dictée',
                    'Produire de courts écrits',
                    'Écouter, dire, participer aux échanges',
                    'Enrichir le vocabulaire et mémoriser l\'orthographe lexicale',
                ],
                'competences': [
                    'Identifier les mots de manière de plus en plus aisée',
                    'Lire à voix haute',
                    'Comprendre un texte',
                    'Devenir lecteur',
                    'Écrire en cursive / encoder / copier / produire',
                    'Écouter pour comprendre / dire pour être compris',
                ],
                'activites': [
                    'Séances quotidiennes de code (CGP)',
                    'Lecture à voix haute guidée',
                    'Questions de compréhension',
                    'Dictées de mots et de phrases',
                    'Production d\'écrits (légendes, messages)',
                    'Jeux de vocabulaire',
                ],
            },
            'Mathématiques': {
                'objectifs': [
                    'Nombres jusqu\'à 100',
                    'Addition et soustraction (sens et techniques)',
                    'Résolution de problèmes simples',
                    'Mesures : longueur, monnaie',
                    'Repérage dans le temps (jours, mois)',
                    'Calcul mental quotidien',
                ],
                'competences': [
                    'Lire, écrire, comparer les nombres',
                    'Calculer mentalement',
                    'Résoudre des problèmes arithmétiques',
                    'Utiliser des instruments de mesure simples',
                ],
                'activites': [
                    'Calcul mental quotidien',
                    'Situations-problèmes illustrées',
                    'Manipulations monétaires',
                    'Frise numérique',
                    'Jeux de dés et cartes',
                ],
            },
            'EMC': {
                'objectifs': [
                    'Se reconnaître comme individu et élève',
                    'Connaissance et maîtrise de soi',
                    'Règles collectives et autonomie',
                    'Règles d\'hygiène et intimité',
                    'Être élève à l\'école de la République / de la communauté',
                ],
                'competences': ['Respecter les règles de classe', 'Identifier ses émotions', 'Coopérer'],
                'activites': ['Conseil de classe', 'Jeux de rôle', 'Affiches de règles co-construites'],
            },
        },
    },
    '2ème année': {
        'label': '2ème année (équivalent CE1)',
        'cycle': 'Cycle 2',
        'matieres': {
            'Français': {
                'objectifs': [
                    'Consolider le décodage et gagner en fluidité',
                    'Lire à voix haute avec davantage d\'aisance',
                    'Comprendre des textes plus longs',
                    'Produire des écrits structurés',
                    'Enrichir vocabulaire et orthographe',
                ],
                'competences': [
                    'Identifier les mots aisément',
                    'Lire à voix haute',
                    'Comprendre un texte',
                    'Produire des écrits',
                    'Participer à des échanges',
                ],
                'activites': [
                    'Entraînement à la fluidité',
                    'Lecture documentaire simple',
                    'Rédaction de textes courts',
                    'Dictées préparées',
                    'Jeux morphologiques',
                ],
            },
            'Mathématiques': {
                'objectifs': [
                    'Nombres jusqu\'à 1 000',
                    'Techniques opératoires (+, −)',
                    'Introduction à la multiplication',
                    'Géométrie : solides et figures',
                    'Grandeurs et mesures',
                ],
                'competences': [
                    'Maîtriser les techniques + et −',
                    'Résoudre des problèmes en plusieurs étapes',
                    'Tracer des figures à la règle',
                    'Mesurer avec règle et balance',
                ],
                'activites': [
                    'Tables d\'addition',
                    'Problèmes en plusieurs étapes',
                    'Trace de figures',
                    'Mesures concrètes',
                ],
            },
            'EMC': {
                'objectifs': [
                    'Respecter les autres (altérité et sociabilité)',
                    'Règles collectives et prise d\'initiative',
                    'Principes et symboles de la République / du pays',
                ],
                'competences': ['Respecter l\'autre', 'Prendre des initiatives', 'Reconnaître des symboles'],
                'activites': ['Débats réglés', 'Projets solidaires', 'Découverte des symboles'],
            },
        },
    },
    '3ème année': {
        'label': '3ème année (équivalent CE2)',
        'cycle': 'Cycle 2',
        'matieres': {
            'Français': {
                'objectifs': [
                    'Lire de manière fluide et écrire des énoncés simples (fin de cycle 2)',
                    'Comprendre des textes variés',
                    'Produire des écrits cohérents',
                    'Grammaire et orthographe de base',
                ],
                'competences': [
                    'Fluidité de lecture',
                    'Compréhension fine',
                    'Production d\'écrits',
                    'Vocabulaire enrichi',
                    'Notions grammaticales de base',
                ],
                'activites': [
                    'Lecture silencieuse et à voix haute',
                    'Comptes rendus de lecture',
                    'Rédactions guidées',
                    'Étude de la langue structurée',
                ],
            },
            'Mathématiques': {
                'objectifs': [
                    'Nombres jusqu\'à 10 000',
                    'Multiplication et division',
                    'Fractions simples (sens)',
                    'Périmètre de figures usuelles',
                    'Problèmes multi-étapes',
                ],
                'competences': [
                    'Maîtriser les tables de multiplication',
                    'Résoudre des situations de partage',
                    'Calculer des périmètres',
                    'Utiliser des stratégies de résolution',
                ],
                'activites': [
                    'Tables de multiplication',
                    'Situations de partage',
                    'Construction de périmètres',
                    'Jeux de stratégie numérique',
                ],
            },
            'EMC': {
                'objectifs': [
                    'Apprendre ensemble et vivre ensemble',
                    'L\'engagement pour le bien commun',
                    'La République et son fonctionnement (notions adaptées)',
                ],
                'competences': ['S\'engager pour le groupe', 'Comprendre des institutions simples'],
                'activites': ['Projets de classe', 'Élections de délégués', 'Visites / témoignages'],
            },
        },
    },
    '4ème année': {
        'label': '4ème année (équivalent CM1)',
        'cycle': 'Cycle 3',
        'matieres': {
            'Français': {
                'objectifs': [
                    'Lire avec fluidité (~110 mots/min en moyenne après préparation)',
                    'Lire et comprendre seul des textes, documents et images',
                    'Culture littéraire (héros, merveilleux, morale, poésie…)',
                    'Écrire à la main de manière fluide ; produire des écrits variés',
                    'Oral : écouter, dire, échanger',
                    'Vocabulaire et grammaire (phrase simple, accords)',
                ],
                'competences': [
                    'Lire avec fluidité',
                    'Lire à voix haute avec expressivité',
                    'Comprendre textes et documents',
                    'Lire une œuvre et s\'en approprier',
                    'Produire des écrits variés',
                    'Identifier les constituants de la phrase simple',
                ],
                'activites': [
                    'Lecture quotidienne (silencieuse et à voix haute)',
                    'Au moins 2 œuvres patrimoniales + 5 ouvrages jeunesse / an',
                    'Écrits réflexifs courts',
                    'Dictées et étude de la langue',
                    'Débats littéraires',
                ],
            },
            'Mathématiques': {
                'objectifs': [
                    'Nombres jusqu\'aux millions',
                    'Fractions et nombres décimaux (introduction)',
                    'Les quatre opérations',
                    'Aires et périmètres',
                    'Proportionnalité simple',
                    'Géométrie plane et solides',
                ],
                'competences': [
                    'Calculer avec les 4 opérations',
                    'Comprendre fractions et décimaux',
                    'Mesurer et calculer des aires',
                    'Résoudre des problèmes de proportionnalité',
                ],
                'activites': [
                    'Calcul posé renforcé',
                    'Problèmes de proportionnalité',
                    'Mesure d\'aires sur quadrillage',
                    'Lecture de graphiques simples',
                ],
            },
            'EMC': {
                'objectifs': [
                    'Faire société : civisme et citoyenneté',
                    'L\'égalité dans la dignité',
                    'Comment faire société',
                ],
                'competences': ['Agir en citoyen de la classe', 'Respecter l\'égalité', 'Débattre'],
                'activites': ['Projets citoyens', 'Étude de situations d\'égalité', 'Débats réglés'],
            },
        },
    },
    '5ème année': {
        'label': '5ème année (équivalent CM2) — préparation CEP',
        'cycle': 'Cycle 3',
        'matieres': {
            'Français': {
                'objectifs': [
                    'Fluidité ~120 mots/min ; compréhension d\'informations explicites et implicites',
                    'Lire des œuvres et s\'en approprier',
                    'Produire des écrits autonomes respectant les codes',
                    'Grammaire : phrase simple consolidée, notions d\'expansion',
                    'Préparation aux écrits et lectures du CEP',
                ],
                'competences': [
                    'Lire avec fluidité et expressivité',
                    'Restituer l\'essentiel d\'un texte',
                    'Produire des écrits variés de façon autonome',
                    'Mobiliser grammaire et orthographe en production',
                ],
                'activites': [
                    'Au moins 3 œuvres patrimoniales + 4 ouvrages jeunesse',
                    'Rédactions type examen',
                    'Compréhension de documents composites',
                    'Entraînement CEP',
                ],
            },
            'Mathématiques': {
                'objectifs': [
                    'Maîtrise des quatre opérations',
                    'Fractions et nombres décimaux',
                    'Proportionnalité et pourcentages simples',
                    'Géométrie plane et solides',
                    'Préparation aux épreuves du CEP',
                ],
                'competences': [
                    'Résoudre des problèmes complexes',
                    'Utiliser fractions et décimaux',
                    'Constructions géométriques précises',
                    'Gérer le temps en situation d\'évaluation',
                ],
                'activites': [
                    'Annales et exercices type CEP',
                    'Problèmes multi-étapes',
                    'Constructions à la règle et au compas',
                    'Entraînement chronométré',
                ],
            },
            'EMC': {
                'objectifs': [
                    'Vivre en République : citoyenneté et nationalité (notions adaptées)',
                    'Libertés et droits fondamentaux',
                    'Respecter les droits de tous',
                    'Laïcité et vivre-ensemble à l\'école',
                ],
                'competences': ['Comprendre des droits et devoirs', 'Respecter les différences', 'Argumenter'],
                'activites': ['Études de cas', 'Charte de classe', 'Projets de solidarité'],
            },
        },
    },
}

# Fusion livrets/guides dans les programmes (après définition)


# Alias rétrocompatibilité
MATH_PROGRAMS = {
    niv: {
        'title': data['matieres'].get('Mathématiques', data['matieres'].get('Mathématiques (premiers outils)', {})).get('objectifs', [''])[0] if False else data['label'] + ' — Mathématiques',
        'objectifs': data['matieres'].get('Mathématiques', data['matieres'].get('Mathématiques (premiers outils)', {})).get('objectifs', []),
        'activites': data['matieres'].get('Mathématiques', data['matieres'].get('Mathématiques (premiers outils)', {})).get('activites', []),
    }
    for niv, data in PROGRAMMES_OFFICIELS.items()
    if 'Mathématiques' in data['matieres'] or 'Mathématiques (premiers outils)' in data['matieres']
}
for niv, data in PROGRAMMES_OFFICIELS.items():
    m = data['matieres'].get('Mathématiques') or data['matieres'].get('Mathématiques (premiers outils)')
    if m:
        MATH_PROGRAMS[niv] = {
            'title': f"Mathématiques — {data['label']}",
            'objectifs': m.get('objectifs', []),
            'activites': m.get('activites', []),
        }



def seed_song_bank():
    """Remplit la banque à partir de COMPTINES si vide."""
    try:
        if scoped_query(SongBank).count() > 0:
            return
        for c in COMPTINES:
            db.session.add(SongBank(
                titre=c.get('titre') or 'Sans titre',
                niveau=c.get('niveau') or '',
                kind=c.get('type') or 'comptine',
                texte=c.get('texte') or '',
                source='programme',
            ))
        db.session.commit()
    except Exception:
        db.session.rollback()


COMPTINES = [
    # —— PS ——
    {'titre': 'Une poule sur un mur', 'niveau': 'PS', 'type': 'comptine',
     'texte': 'Une poule sur un mur\nQui picote du pain dur\nPicoti, picota\nLève la queue et puis s\'en va.'},
    {'titre': 'Ainsi font font font', 'niveau': 'PS', 'type': 'comptine',
     'texte': 'Ainsi font, font, font\nLes petites marionnettes\nAinsi font, font, font\nTrois petits tours et puis s\'en vont.'},
    {'titre': 'Am stram gram', 'niveau': 'PS', 'type': 'comptine',
     'texte': 'Am stram gram\nPic et pic et colegram\nBour et bour et ratatam\nAm stram gram.'},
    {'titre': 'Bateau sur l\'eau', 'niveau': 'PS', 'type': 'comptine',
     'texte': 'Bateau sur l\'eau\nLa rivière, la rivière\nBateau sur l\'eau\nLa rivière au bord de l\'eau.'},
    {'titre': 'Savez-vous planter les choux', 'niveau': 'PS', 'type': 'chant',
     'texte': 'Savez-vous planter les choux\nÀ la mode, à la mode\nSavez-vous planter les choux\nÀ la mode de chez nous ?\nOn les plante avec le doigt…'},
    {'titre': 'Tapent petits doigts', 'niveau': 'PS', 'type': 'comptine',
     'texte': 'Tapent, tapent petits doigts\nDoigts de la main, doigts du pied\nTourne, tourne petit pouce\nEt les autres font comme ça.'},
    # —— MS ——
    {'titre': 'Un kilomètre à pied', 'niveau': 'MS', 'type': 'chant',
     'texte': 'Un kilomètre à pied, ça use, ça use\nUn kilomètre à pied, ça use les souliers.\nDeux kilomètres à pied…'},
    {'titre': '1, 2, 3, nous irons au bois', 'niveau': 'MS', 'type': 'comptine',
     'texte': '1, 2, 3, nous irons au bois\n4, 5, 6, cueillir des cerises\n7, 8, 9, dans mon panier neuf\n10, 11, 12, elles seront toutes rouges.'},
    {'titre': 'Pomme de reinette', 'niveau': 'MS', 'type': 'comptine',
     'texte': 'Pomme de reinette et pomme d\'api\nTapi tapi tapi\nPomme de reinette et pomme d\'api\nTapi tapi ta.'},
    {'titre': 'Bonjour, bonjour', 'niveau': 'MS', 'type': 'chant',
     'texte': 'Bonjour, bonjour, les amis\nBonjour, bonjour, comment allez-vous ?\nTrès bien, merci, et vous ?'},
    {'titre': 'Les petites marionnettes', 'niveau': 'MS', 'type': 'comptine',
     'texte': 'Ainsi font, font, font\nLes petites marionnettes\nElles font, font, font\nTrois petits tours et puis s\'en vont\nElles reprennent, prennent, prennent\nLe chemin des écoliers…'},
    {'titre': 'Il court, il court le furet', 'niveau': 'MS', 'type': 'chant',
     'texte': 'Il court, il court, le furet\nLe furet du bois, mesdames\nIl court, il court, le furet\nLe furet du bois joli.'},
    # —— GS ——
    {'titre': 'Frère Jacques', 'niveau': 'GS', 'type': 'chant',
     'texte': 'Frère Jacques, Frère Jacques\nDormez-vous ? Dormez-vous ?\nSonnez les matines, sonnez les matines\nDing ding dong, ding ding dong.'},
    {'titre': 'Le fermier dans son pré', 'niveau': 'GS', 'type': 'chant',
     'texte': 'Le fermier dans son pré\nA planté des petits pois\nQui poussent, poussent, poussent\nEt font de grands pois.'},
    {'titre': 'Un éléphant qui se balançait', 'niveau': 'GS', 'type': 'comptine',
     'texte': 'Un éléphant qui se balançait\nSur une toile, toile, toile, toile d\'araignée\nC\'était un jeu tellement amusant\nQue tout l\'après-midi il s\'est balancé.'},
    {'titre': 'La ronde des lettres', 'niveau': 'GS', 'type': 'comptine',
     'texte': 'A, B, C, D, E, F, G\nH, I, J, K, L, M, N, O, P\nQ, R, S, T, U, V\nW, X, Y, Z\nMaintenant je connais mon alphabet !'},
    {'titre': 'Head, shoulders (EN)', 'niveau': 'GS', 'type': 'chant',
     'texte': 'Head, shoulders, knees and toes\nKnees and toes\nHead, shoulders, knees and toes\nEyes and ears and mouth and nose.'},
    {'titre': 'Meunier tu dors', 'niveau': 'GS', 'type': 'chant',
     'texte': 'Meunier, tu dors, ton moulin va trop vite\nMeunier, tu dors, ton moulin va trop fort.'},
    {'titre': 'Compter jusqu\'à dix', 'niveau': 'GS', 'type': 'comptine',
     'texte': 'Un, deux, trois\nJ\'irai dans les bois\nQuatre, cinq, six\nCueillir des cerises\nSept, huit, neuf\nDans mon panier neuf\nDix, onze, douze\nElles seront toutes rouges.'},
    # —— 1ère année (CP) ——
    {'titre': 'Au clair de la lune', 'niveau': '1ère année', 'type': 'chant',
     'texte': 'Au clair de la lune\nMon ami Pierrot\nPrête-moi ta plume\nPour écrire un mot.\nMa chandelle est morte\nJe n\'ai plus de feu\nOuvre-moi ta porte\nPour l\'amour de Dieu.'},
    {'titre': 'Dans la forêt lointaine', 'niveau': '1ère année', 'type': 'chant',
     'texte': 'Dans la forêt lointaine\nOn entend le coucou\nDu haut de son grand chêne\nIl répond au hibou\nCoucou, coucou…'},
    {'titre': 'Alphabet chanté', 'niveau': '1ère année', 'type': 'chant',
     'texte': 'A B C D E F G\nH I J K L M N O P\nQ R S T U V\nW X Y et Z\nC\'est l\'alphabet, je le connais !'},
    {'titre': 'Les jours de la semaine', 'niveau': '1ère année', 'type': 'comptine',
     'texte': 'Lundi, mardi, mercredi\nJeudi, vendredi, samedi\nEt dimanche terminé\nLa semaine est passée.'},
    {'titre': 'Comptine des sons', 'niveau': '1ère année', 'type': 'comptine',
     'texte': 'Le [a] de papa, le [i] de pipi\nLe [o] de vélo, le [u] de tortue\nJ\'écoute les sons, je les reconnais\nPour bien apprendre à lire, c\'est vrai !'},
    # —— 2ème année (CE1) ——
    {'titre': 'À la claire fontaine', 'niveau': '2ème année', 'type': 'chant',
     'texte': 'À la claire fontaine\nM\'en allant promener\nJ\'ai trouvé l\'eau si belle\nQue je m\'y suis baigné…'},
    {'titre': 'Gentil coquelicot', 'niveau': '2ème année', 'type': 'chant',
     'texte': 'J\'ai descendu dans mon jardin\nPour y cueillir du thym\nGentil coquelicot, mesdames\nGentil coquelicot.'},
    {'titre': 'La marelle chantée', 'niveau': '2ème année', 'type': 'comptine',
     'texte': 'Un, deux, trois, j\'irai dans les bois\nQuatre, cinq, six, cueillir des cerises\nSept, huit, neuf, dans mon panier neuf\nDix, j\'arrive enfin !'},
    {'titre': 'Chanson des mois', 'niveau': '2ème année', 'type': 'chant',
     'texte': 'Janvier, février, mars et avril\nMai, juin, juillet font mûrir le blé\nAoût, septembre, octobre aussi\nNovembre, décembre : l\'année est finie.'},
    # —— 3ème année (CE2) ——
    {'titre': 'Il était un petit navire', 'niveau': '3ème année', 'type': 'chant',
     'texte': 'Il était un petit navire\nQui n\'avait ja-ja-jamais navigué\nOhé ! Ohé !'},
    {'titre': 'La chenille', 'niveau': '3ème année', 'type': 'chant',
     'texte': 'Une chenille se balançait\nSur une feuille, feuille, feuille\nC\'était un jeu si amusant\nQu\'une autre chenille est montée…'},
    {'titre': 'Comptine multiplicative', 'niveau': '3ème année', 'type': 'comptine',
     'texte': '2 et 2 font 4, 4 et 4 font 8\n8 et 8 font 16, 16 et 16 font 32\nJe multiplie, je progresse\nLes tables dans ma tête !'},
    {'titre': 'Vent frais', 'niveau': '3ème année', 'type': 'chant',
     'texte': 'Vent frais, vent du matin\nVent qui souffle au sommet des grands pins\nJoie du vent qui passe\nAllons dans le grand vent !'},
    # —— 4ème année (CM1) ——
    {'titre': 'Le temps des cerises', 'niveau': '4ème année', 'type': 'chant',
     'texte': 'Quand nous chanterons le temps des cerises\nEt gai rossignol et merle moqueur\nSeront tous en fête…'},
    {'titre': 'Chant des poètes', 'niveau': '4ème année', 'type': 'chant',
     'texte': 'Les mots dansent, les rimes chantent\nSur la page blanche du cahier\nPoésie, ouvre tes ailes\nEt fais voyager nos pensées.'},
    {'titre': 'Géométrie en chanson', 'niveau': '4ème année', 'type': 'comptine',
     'texte': 'Le carré a quatre côtés égaux\nLe rectangle deux longs, deux petits\nLe triangle trois côtés bien rangés\nLe cercle n\'en finit plus de tourner !'},
    {'titre': 'La Marseillaise (extrait pédagogique)', 'niveau': '4ème année', 'type': 'chant',
     'texte': 'Allons enfants de la Patrie\nLe jour de gloire est arrivé…\n(extrait — éducation civique / culture)'},
    # —— 5ème année (CM2) ——
    {'titre': 'Hymne à la joie (thème)', 'niveau': '5ème année', 'type': 'chant',
     'texte': 'Chantons tous en chœur la joie\nQui unit les cœurs des hommes\nAmis, laissons la colère\nEt marchons vers la lumière.'},
    {'titre': 'Chant pour le CEP', 'niveau': '5ème année', 'type': 'chant',
     'texte': 'Courage, courage, les candidats\nLe CEP n\'est pas si loin\nOn révise, on s\'entraîne\nEt la réussite sera nôtre !'},
    {'titre': 'Les continents', 'niveau': '5ème année', 'type': 'comptine',
     'texte': 'Afrique, Amérique, Antarctique\nAsie, Europe et Océanie\nSix continents sur la Terre\nJe les connais, je les situe !'},
    {'titre': 'Poème-comptine des fractions', 'niveau': '5ème année', 'type': 'comptine',
     'texte': 'Un demi, c\'est la moitié\nUn tiers, c\'est trois parts égales\nUn quart, quatre parts du gâteau\nLes fractions, c\'est pas compliqué !'},
]

QUOTES_JOUR = [
    '« L\'éducation est l\'arme la plus puissante pour changer le monde. » — Nelson Mandela',
    '« Chaque enfant est un explorateur. » — U nengue',
    '« Apprendre, c\'est allumer une flamme, non remplir un vase. »',
    '« La patience est un arbre dont la racine est amère, mais le fruit est doux. »',
    '« Un livre ouvert, c\'est une bouche qui parle. »',
    '« L\'école du Gabon forme les citoyens de demain. » — U nengue',
    '« Petit à petit, l\'oiseau fait son nid. »',
    '« Qui veut voyager loin ménage sa monture — et révise chaque jour. »',
]

CALENDRIER_SCOLAIRE_GABON = [
    {'mois': 'Septembre', 'evenements': ['Rentrée des classes', 'Constitution des effectifs']},
    {'mois': 'Octobre', 'evenements': ['Évaluations de début d\'année', 'Réunion parents']},
    {'mois': 'Novembre', 'evenements': ['Palier / période 1', 'Fête nationale (selon calendrier)']},
    {'mois': 'Décembre', 'evenements': ['Vacances de Noël', 'Bilans de période']},
    {'mois': 'Janvier', 'evenements': ['Reprise des cours', 'Évaluations']},
    {'mois': 'Février', 'evenements': ['Période 2', 'Activités culturelles']},
    {'mois': 'Mars', 'evenements': ['Préparation CEP (5ème année)', 'Évaluations']},
    {'mois': 'Avril', 'evenements': ['Vacances de Pâques', 'Révisions CEP']},
    {'mois': 'Mai', 'evenements': ['Examens blancs CEP', 'Fête du travail']},
    {'mois': 'Juin', 'evenements': ['Examens CEP', 'Conseils de classe', 'Fin d\'année']},
    {'mois': 'Juillet', 'evenements': ['Vacances scolaires', 'Résultats']},
]

@app.route('/dictionnaire')
@login_required
def dictionnaire():
    q = (request.args.get('q') or '').strip().lower()
    letter = (request.args.get('lettre') or '').strip().lower()
    results = []
    source = DICTIONARY_WORDS
    if letter and len(letter) == 1:
        source = [(fr, en) for fr, en in DICTIONARY_WORDS if fr.lower().startswith(letter)]
    if q:
        for fr, en in source:
            if q in fr.lower() or q in en.lower():
                results.append((fr, en))
    else:
        results = list(source)
    # pagination simple
    page = request.args.get('page', 1, type=int) or 1
    per = 50
    total_r = len(results)
    pages = max(1, (total_r + per - 1) // per)
    page = max(1, min(page, pages))
    chunk = results[(page-1)*per:page*per]
    letters = sorted({fr[0].lower() for fr, _ in DICTIONARY_WORDS if fr})
    return render_template(
        'dictionnaire.html', results=chunk, q=q, total=len(DICTIONARY_WORDS),
        total_r=total_r, page=page, pages=pages, letter=letter, letters=letters,
    )

@app.route('/programmes-maths')
@login_required
def programmes_maths():
    return redirect(url_for('programmes', matiere='Mathématiques'))


@app.route('/programmes/pdf/<path:filename>')
@login_required
def programme_pdf(filename):
    """Téléchargement / consultation des PDF officiels."""
    safe = secure_filename(filename.replace('..', ''))
    folder = os.path.join(app.root_path, 'static', 'programmes')
    path = os.path.join(folder, safe)
    if not os.path.isfile(path):
        flash('Document introuvable.', 'danger')
        return redirect(url_for('programmes'))
    return send_from_directory(folder, safe, as_attachment=False, mimetype='application/pdf')


@app.route('/programmes')
@login_required
def programmes():
    niveau = request.args.get('niveau', '')
    matiere = request.args.get('matiere', '')
    # Vue d'accueil : toutes les classes si aucun niveau
    if not niveau or niveau not in PROGRAMMES_OFFICIELS:
        return render_template(
            'programmes.html',
            programmes=PROGRAMMES_OFFICIELS,
            niveau='',
            matiere='',
            matieres=[],
            content={},
            niveaux=list(PROGRAMMES_OFFICIELS.keys()),
            data=None,
            vue='accueil',
            pdfs=[],
            all_pdfs=PROGRAMME_PDFS,
        )
    data = PROGRAMMES_OFFICIELS[niveau]
    matieres = list(data['matieres'].keys())
    if matiere and matiere not in data['matieres']:
        matiere = ''
    content = data['matieres'].get(matiere, {}) if matiere else {}
    pdfs = PROGRAMME_PDFS.get(niveau, [])
    return render_template(
        'programmes.html',
        programmes=PROGRAMMES_OFFICIELS,
        niveau=niveau,
        matiere=matiere,
        matieres=matieres,
        content=content,
        niveaux=list(PROGRAMMES_OFFICIELS.keys()),
        data=data,
        vue='classe' if not matiere else 'matiere',
        pdfs=pdfs,
        all_pdfs=PROGRAMME_PDFS,
    )

@app.route('/api/programme-suggestions', methods=['GET', 'POST'])
@login_required
def api_programme_suggestions():
    """JSON pour préremplir fiches pédagogiques / préparations."""
    try:
        niveau = (request.args.get('niveau') or request.form.get('niveau') or '').strip()
        matiere = (request.args.get('matiere') or request.form.get('matiere') or '').strip()
        # normaliser apostrophes / espaces
        niveau_key = niveau.replace("'", "'").replace("'", "'")
        data = PROGRAMMES_OFFICIELS.get(niveau_key) or PROGRAMMES_OFFICIELS.get(niveau)
        if not data:
            # essai approximatif
            for k in PROGRAMMES_OFFICIELS:
                if niveau.lower() in k.lower() or k.lower() in niveau.lower():
                    data = PROGRAMMES_OFFICIELS[k]
                    niveau_key = k
                    break
        if not data:
            return jsonify({'ok': False, 'error': 'niveau inconnu: ' + niveau})
        mdata = None
        mat_l = matiere.lower()
        for k, v in data['matieres'].items():
            kl = k.lower()
            if mat_l in kl or kl in mat_l or (mat_l[:4] and mat_l[:4] in kl):
                mdata = v
                break
        if not mdata and data['matieres']:
            # Français / Mathématiques prioritaires
            for pref in ['Français', 'Mathématiques', 'Langage oral et écrit', 'Mathématiques (premiers outils)']:
                if pref in data['matieres']:
                    mdata = data['matieres'][pref]
                    break
            if not mdata:
                mdata = list(data['matieres'].values())[0]
        if not mdata:
            return jsonify({'ok': False, 'error': 'matière introuvable'})
        return jsonify({
            'ok': True,
            'niveau': niveau_key or niveau,
            'cycle': data.get('cycle', ''),
            'objectifs': mdata.get('objectifs', []),
            'competences': mdata.get('competences', []),
            'activites': mdata.get('activites', []),
            'pdf': mdata.get('pdf', ''),
            'type_doc': mdata.get('type_doc', 'programme'),
            'matiere': next((k for k, v in data['matieres'].items() if v is mdata), matiere),
        })
    except Exception as e:
        return jsonify({'ok': False, 'error': str(e)})


@app.route('/comptines', methods=['GET', 'POST'])
@login_required
def comptines():
    """Banque de comptines & chants — toujours accessible (fallback liste intégrée)."""
    niveaux = ['PS','MS','GS','1ère année','2ème année','3ème année','4ème année','5ème année']
    # Créer la table si besoin
    try:
        db.create_all()
    except Exception:
        pass
    if request.method == 'POST':
        if session.get('role') != 'Directeur':
            flash('Réservé au directeur.', 'danger')
            return redirect(url_for('comptines'))
        titre = request.form.get('titre', '').strip()
        if titre:
            try:
                db.session.add(SongBank(
                    titre=titre,
                    niveau=request.form.get('niveau', '').strip(),
                    kind=request.form.get('type', 'comptine').strip() or 'comptine',
                    texte=request.form.get('texte', '').strip(),
                    source=request.form.get('source', 'ecole').strip() or 'ecole',
                ))
                db.session.commit()
                flash('Ajouté à la banque.', 'success')
            except Exception as e:
                db.session.rollback()
                flash('Erreur ajout: ' + str(e), 'danger')
        return redirect(url_for('comptines'))

    niveau = request.args.get('niveau', '')
    type_f = request.args.get('type', '')
    q = (request.args.get('q') or '').strip().lower()

    # 1) Essayer seed + lecture BDD
    items = []
    try:
        seed_song_bank()
        query = scoped_query(SongBank)
        if niveau:
            query = query.filter_by(niveau=niveau)
        if type_f:
            query = query.filter_by(kind=type_f)
        rows = query.order_by(SongBank.niveau, SongBank.titre).all()
        for r in rows:
            if q and q not in (r.titre or '').lower() and q not in (r.texte or '').lower():
                continue
            items.append({
                'id': r.id,
                'titre': r.titre,
                'niveau': r.niveau or '',
                'type': r.kind or 'comptine',
                'texte': r.texte or '',
                'source': r.source or '',
            })
    except Exception as e:
        print('comptines DB:', e)
        items = []

    # 2) Fallback liste intégrée COMPTINES
    if not items:
        for c in COMPTINES:
            if niveau and c.get('niveau') != niveau:
                continue
            if type_f and c.get('type') != type_f:
                continue
            if q and q not in (c.get('titre') or '').lower() and q not in (c.get('texte') or '').lower():
                continue
            items.append({
                'id': None,
                'titre': c.get('titre', ''),
                'niveau': c.get('niveau', ''),
                'type': c.get('type', 'comptine'),
                'texte': c.get('texte', ''),
                'source': 'programme',
            })

    return render_template('comptines.html', items=items, niveau=niveau, type_f=type_f, q=q, niveaux=niveaux)

@app.route('/comptines/ajouter', methods=['POST'])
@login_required
def comptines_ajouter():
    if session.get('role') != 'Directeur':
        flash('Réservé au directeur.', 'danger')
        return redirect(url_for('comptines'))
    titre = request.form.get('titre', '').strip()
    if not titre:
        flash('Titre obligatoire.', 'danger')
        return redirect(url_for('comptines'))
    s = SongBank(
        titre=titre,
        niveau=request.form.get('niveau', '').strip(),
        kind=request.form.get('type', 'comptine').strip() or 'comptine',
        texte=request.form.get('texte', '').strip(),
        source=request.form.get('source', 'ecole').strip() or 'ecole',
    )
    db.session.add(s)
    db.session.commit()
    flash('Ajouté à la banque de comptines & chants.', 'success')
    return redirect(url_for('comptines', niveau=s.niveau or None))

@app.route('/comptines/<int:id>/supprimer', methods=['GET', 'POST'])
@login_required
def comptines_supprimer(id):
    if session.get('role') != 'Directeur':
        flash('Réservé au directeur.', 'danger')
        return redirect(url_for('comptines'))
    s = scoped_query(SongBank).get_or_404(id)
    db.session.delete(s)
    db.session.commit()
    flash('Supprimé de la banque.', 'success')
    return redirect(url_for('comptines'))

@app.route('/comptines/recharger-programmes')
@login_required
def comptines_recharger():
    """Réinjecte les titres programme manquants (sans doublons de titre+niveau)."""
    if session.get('role') != 'Directeur':
        flash('Réservé au directeur.', 'danger')
        return redirect(url_for('comptines'))
    existing = {(x.titre, x.niveau) for x in scoped_query(SongBank).all()}
    n = 0
    for c in COMPTINES:
        key = (c.get('titre'), c.get('niveau'))
        if key in existing:
            continue
        db.session.add(SongBank(
            titre=c.get('titre') or 'Sans titre',
            niveau=c.get('niveau') or '',
            kind=c.get('type') or 'comptine',
            texte=c.get('texte') or '',
            source='programme',
        ))
        n += 1
    db.session.commit()
    flash(f'{n} titre(s) programme ajouté(s) à la banque.', 'success')
    return redirect(url_for('comptines'))



@app.route('/langues')
@login_required
def langues():
    """Hub langues étrangères / locales."""
    return render_template(
        'langues.html',
        n_ipunu=len(IPUNU_DICT),
        n_hebreu=len(HEBREU_DICT),
        n_lecons_ipunu=len(IPUNU_LECONS),
        n_lecons_hebreu=len(HEBREU_LECONS),
        has_ipunu_pdf=os.path.isfile(os.path.join(app.root_path, 'static', 'programmes', 'langue-ipunu.pdf')),
        has_hebreu_pdf=os.path.isfile(os.path.join(app.root_path, 'static', 'programmes', 'langue-hebreu.pdf')),
    )

@app.route('/ipunu')
@login_required
def ipunu():
    """Accueil apprentissage langue ipunu (Punu — Gabon)."""
    return render_template(
        'ipunu.html',
        n_mots=len(IPUNU_DICT),
        n_lecons=len(IPUNU_LECONS),
        has_pdf=os.path.isfile(os.path.join(app.root_path, 'static', 'programmes', 'langue-ipunu.pdf')),
        has_pron=bool(IPUNU_PRON),
    )

@app.route('/ipunu/dictionnaire')
@login_required
def ipunu_dictionnaire():
    q = (request.args.get('q') or '').strip().lower()
    cat = (request.args.get('cat') or '').strip()
    items = IPUNU_DICT
    cats = sorted({x.get('cat', '') for x in items if x.get('cat')})
    if cat:
        items = [x for x in items if x.get('cat') == cat]
    if q:
        items = [x for x in items if q in (x.get('fr') or '').lower() or q in (x.get('ipunu') or '').lower()]
    page = request.args.get('page', 1, type=int) or 1
    per = 40
    total_r = len(items)
    pages = max(1, (total_r + per - 1) // per)
    page = max(1, min(page, pages))
    chunk = items[(page-1)*per:page*per]
    return render_template(
        'ipunu_dictionnaire.html', items=chunk, q=q, cat=cat, cats=cats,
        total=len(IPUNU_DICT), total_r=total_r, page=page, pages=pages,
    )



@app.route('/ipunu/cours')
@login_required
def ipunu_cours():
    return render_template('ipunu_cours.html', cours=IPUNU_COURS or {})

@app.route('/ipunu/conjugaisons')
@login_required
def ipunu_conjugaisons():
    c = IPUNU_COURS or {}
    return render_template('ipunu_conjugaisons.html', conjugaisons=c.get('conjugaisons', []), pronoms=c.get('pronoms', {}))

@app.route('/ipunu/alphabet')
@login_required
def ipunu_alphabet():
    c = IPUNU_COURS or {}
    return render_template('ipunu_alphabet.html', alphabet=c.get('alphabet', {}), orthographe=c.get('orthographe', []))

@app.route('/ipunu/exercices')
@login_required
def ipunu_exercices():
    return render_template('ipunu_exercices.html', exercices=IPUNU_EXERCICES)

@app.route('/ipunu/exercices/<int:eid>')
@login_required
def ipunu_exercice_detail(eid):
    ex = next((e for e in IPUNU_EXERCICES if e.get('id') == eid), None)
    if not ex:
        flash('Exercice introuvable.', 'danger')
        return redirect(url_for('ipunu_exercices'))
    return render_template('ipunu_exercice_detail.html', ex=ex, exercices=IPUNU_EXERCICES)

@app.route('/ipunu/evaluations')
@login_required
def ipunu_evaluations():
    return render_template('ipunu_evaluations.html', evaluations=IPUNU_EVALS)

@app.route('/ipunu/evaluations/<int:eid>', methods=['GET', 'POST'])
@login_required
def ipunu_evaluation_detail(eid):
    ev = next((e for e in IPUNU_EVALS if e.get('id') == eid), None)
    if not ev:
        flash('Évaluation introuvable.', 'danger')
        return redirect(url_for('ipunu_evaluations'))
    result = None
    if request.method == 'POST':
        score = 0
        total = len(ev.get('questions', []))
        details = []
        for i, q in enumerate(ev.get('questions', [])):
            try:
                ans = int(request.form.get(f'q{i}', -1))
            except ValueError:
                ans = -1
            ok = ans == q.get('a')
            if ok:
                score += 1
            details.append({'q': q['q'], 'ok': ok, 'correct': q['choices'][q['a']], 'yours': q['choices'][ans] if 0 <= ans < len(q['choices']) else '—'})
        result = {'score': score, 'total': total, 'pct': round(100 * score / total) if total else 0, 'details': details}
    return render_template('ipunu_evaluation_detail.html', ev=ev, result=result)

@app.route('/ipunu/prononciation')
@login_required
def ipunu_prononciation():
    return render_template('ipunu_prononciation.html', pron=IPUNU_PRON or {})

@app.route('/ipunu/lecons')
@login_required
def ipunu_lecons():
    return render_template('ipunu_lecons.html', lecons=IPUNU_LECONS)

@app.route('/ipunu/lecons/<int:lid>')
@login_required
def ipunu_lecon_detail(lid):
    lecon = next((l for l in IPUNU_LECONS if l.get('id') == lid), None)
    if not lecon:
        flash('Leçon introuvable.', 'danger')
        return redirect(url_for('ipunu_lecons'))
    return render_template('ipunu_lecon_detail.html', lecon=lecon, lecons=IPUNU_LECONS)

@app.route('/ipunu/pdf')
@login_required
def ipunu_pdf():
    folder = os.path.join(app.root_path, 'static', 'programmes')
    fname = 'langue-ipunu.pdf'
    path = os.path.join(folder, fname)
    if not os.path.isfile(path):
        flash('Le PDF ipunu n\'est pas encore déposé. Envoyez le fichier à intégrer (nom : langue-ipunu.pdf).', 'warning')
        return redirect(url_for('ipunu'))
    return send_from_directory(folder, fname, as_attachment=False, mimetype='application/pdf')


@app.route('/hebreu')
@login_required
def hebreu():
    return render_template(
        'hebreu.html',
        n_mots=len(HEBREU_DICT),
        n_lecons=len(HEBREU_LECONS),
        has_pdf=os.path.isfile(os.path.join(app.root_path, 'static', 'programmes', 'langue-hebreu.pdf')),
    )

@app.route('/hebreu/dictionnaire')
@login_required
def hebreu_dictionnaire():
    q = (request.args.get('q') or '').strip().lower()
    cat = (request.args.get('cat') or '').strip()
    items = HEBREU_DICT
    cats = sorted({x.get('cat', '') for x in items if x.get('cat')})
    if cat:
        items = [x for x in items if x.get('cat') == cat]
    if q:
        items = [x for x in items if q in (x.get('fr') or '').lower()
                 or q in (x.get('he') or '').lower()
                 or q in (x.get('he_script') or '')]
    page = request.args.get('page', 1, type=int) or 1
    per = 40
    total_r = len(items)
    pages = max(1, (total_r + per - 1) // per)
    page = max(1, min(page, pages))
    chunk = items[(page-1)*per:page*per]
    return render_template(
        'hebreu_dictionnaire.html', items=chunk, q=q, cat=cat, cats=cats,
        total=len(HEBREU_DICT), total_r=total_r, page=page, pages=pages,
    )

@app.route('/hebreu/lecons')
@login_required
def hebreu_lecons():
    return render_template('hebreu_lecons.html', lecons=HEBREU_LECONS)

@app.route('/hebreu/lecons/<int:lid>')
@login_required
def hebreu_lecon_detail(lid):
    lecon = next((l for l in HEBREU_LECONS if l.get('id') == lid), None)
    if not lecon:
        flash('Leçon introuvable.', 'danger')
        return redirect(url_for('hebreu_lecons'))
    return render_template('hebreu_lecon_detail.html', lecon=lecon, lecons=HEBREU_LECONS)

@app.route('/hebreu/pdf')
@login_required
def hebreu_pdf():
    folder = os.path.join(app.root_path, 'static', 'programmes')
    fname = 'langue-hebreu.pdf'
    if not os.path.isfile(os.path.join(folder, fname)):
        flash('PDF hébreu introuvable.', 'warning')
        return redirect(url_for('hebreu'))
    return send_from_directory(folder, fname, as_attachment=False, mimetype='application/pdf')

@app.route('/calendrier-scolaire')
@login_required
def calendrier_scolaire():
    holidays = scoped_query(Holiday).order_by(Holiday.date).all()
    return render_template('calendrier_scolaire.html',
                           calendrier=CALENDRIER_SCOLAIRE_GABON,
                           holidays=holidays)

@app.route('/espace-parents', methods=['GET', 'POST'])
def espace_parents():
    """Accès parents par matricule + code PIN (sans compte enseignant)."""
    student = None
    error = None
    if request.method == 'POST':
        mat = (request.form.get('matricule') or '').strip()
        pin = (request.form.get('pin') or '').strip()
        student = scoped_query(Student).filter_by(matricule=mat).first()
        if not student:
            error = 'Matricule introuvable.'
            student = None
        elif not student.parent_pin or student.parent_pin != pin:
            error = 'Code PIN incorrect. Demandez-le à l\'école.'
            student = None
        else:
            session['parent_ok'] = True
            session['parent_student_id'] = student.id
    return render_template('espace_parents.html', student=student, error=error)

@app.route('/export/eleves.xlsx')
@login_required
def export_eleves_xlsx():
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill, Alignment
    except ImportError:
        flash('openpyxl non installé. Ajoutez-le dans requirements.txt', 'danger')
        return redirect(url_for('eleves'))
    if session.get('role') == 'Enseignant':
        u = User.query.get(session.get('user_id'))
        students = scoped_query(Student).filter_by(class_id=u.class_id).order_by(Student.last_name).all() if u else []
    else:
        students = scoped_query(Student).order_by(Student.last_name).all()
    wb = Workbook()
    ws = wb.active
    ws.title = 'Élèves'
    headers = ['Matricule', 'Nom', 'Prénom', 'Classe', 'Niveau', 'Sexe', 'Né(e) le',
               'Lieu de naissance', 'Parent', 'Téléphone', 'Statut', 'PIN parents']
    ws.append(headers)
    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='C026D3')
    for s in students:
        ws.append([
            s.matricule or '', s.last_name or '', s.first_name or '',
            s.classroom.name if s.classroom else '',
            s.classroom.level if s.classroom else '',
            s.gender or '',
            s.birth_date.strftime('%d/%m/%Y') if s.birth_date else '',
            s.birth_place or '', s.parent_name or '', s.parent_phone or '',
            s.status or '', getattr(s, 'parent_pin', '') or '',
        ])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
                     as_attachment=True, download_name='eleves_u_nengue.xlsx')

@app.route('/export/classes.xlsx')
@login_required
def export_classes_xlsx():
    try:
        from openpyxl import Workbook
        from openpyxl.styles import Font, PatternFill
    except ImportError:
        flash('openpyxl manquant.', 'danger')
        return redirect(url_for('classes'))
    wb = Workbook()
    ws = wb.active
    ws.title = 'Classes'
    ws.append(['Classe', 'Niveau', 'Enseignant', 'Effectif'])
    for cell in ws[1]:
        cell.font = Font(bold=True, color='FFFFFF')
        cell.fill = PatternFill('solid', fgColor='C026D3')
    for r in scoped_query(ClassRoom).order_by(ClassRoom.level, ClassRoom.name).all():
        n = scoped_query(Student).filter_by(class_id=r.id).count()
        ws.append([r.name, r.level, r.teacher or '', n])
    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return send_file(buf, as_attachment=True, download_name='classes_u_nengue.xlsx',
                     mimetype='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')



# ==================== FICHES RITUELS & PRÉPARATION ====================

@app.route('/fiches-rituels')
@login_required
def fiches_rituels():
    rooms = scoped_query(ClassRoom).order_by(ClassRoom.level, ClassRoom.name).all()
    if session.get('role') == 'Enseignant':
        u = User.query.get(session.get('user_id'))
        if u and u.class_id:
            rooms = [r for r in rooms if r.id == u.class_id]
    class_id = request.args.get('class_id', type=int)
    q = scoped_query(RitualSheet).order_by(RitualSheet.date.desc(), RitualSheet.created_at.desc())
    if class_id:
        q = q.filter_by(class_id=class_id)
    elif session.get('role') == 'Enseignant':
        u = User.query.get(session.get('user_id'))
        if u and u.class_id:
            q = q.filter_by(class_id=u.class_id)
    sheets = q.limit(100).all()
    return render_template('fiches_rituels.html', sheets=sheets, rooms=rooms, class_id=class_id)

@app.route('/fiches-rituels/nouvelle', methods=['GET', 'POST'])
@app.route('/fiches-rituels/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def fiche_rituel_form(id=None):
    import json
    sheet = scoped_query(RitualSheet).get(id) if id else None
    rooms = scoped_query(ClassRoom).order_by(ClassRoom.level, ClassRoom.name).all()
    if session.get('role') == 'Enseignant':
        u = User.query.get(session.get('user_id'))
        if u and u.class_id:
            rooms = [r for r in rooms if r.id == u.class_id]
    if request.method == 'POST':
        if not sheet:
            sheet = RitualSheet(created_by=session.get('user_id'))
            db.session.add(sheet)
        sheet.class_id = request.form.get('class_id', type=int) or None
        d = request.form.get('date') or ''
        try:
            sheet.date = datetime.strptime(d, '%Y-%m-%d').date() if d else datetime.utcnow().date()
        except Exception:
            sheet.date = datetime.utcnow().date()
        sheet.notes = request.form.get('notes', '').strip()
        durs = request.form.getlist('r_duration[]')
        titles = request.form.getlist('r_title[]')
        objs = request.form.getlist('r_objective[]')
        teachs = request.form.getlist('r_teacher[]')
        studs = request.form.getlist('r_student[]')
        items = []
        for i in range(max(len(durs), len(titles), 1)):
            title = (titles[i] if i < len(titles) else '').strip()
            duration = (durs[i] if i < len(durs) else '').strip()
            objective = (objs[i] if i < len(objs) else '').strip()
            teacher_role = (teachs[i] if i < len(teachs) else '').strip()
            student_role = (studs[i] if i < len(studs) else '').strip()
            if not any([title, duration, objective, teacher_role, student_role]):
                continue
            items.append({
                'duration': duration,
                'title': title,
                'objective': objective,
                'teacher_role': teacher_role,
                'student_role': student_role,
            })
        if not items:
            flash('Ajoutez au moins un rituel (titre ou durée).', 'danger')
            return redirect(request.url)
        sheet.items_json = json.dumps(items, ensure_ascii=False)
        # Compat champs simples = 1er rituel
        first = items[0]
        sheet.duration = first.get('duration', '')
        sheet.title = first.get('title', '')
        sheet.objective = first.get('objective', '')
        sheet.teacher_role = first.get('teacher_role', '')
        sheet.student_role = first.get('student_role', '')
        db.session.commit()
        flash(f'{len(items)} rituel(s) enregistré(s) pour cette journée.', 'success')
        return redirect(url_for('fiche_rituel_pdf', id=sheet.id))
    items = sheet.items() if sheet else [
        {'duration': '', 'title': '', 'objective': '', 'teacher_role': '', 'student_role': ''},
        {'duration': '', 'title': '', 'objective': '', 'teacher_role': '', 'student_role': ''},
    ]
    return render_template('fiche_rituel_form.html', sheet=sheet, rooms=rooms, items=items)

@app.route('/fiches-rituels/<int:id>/pdf')
@login_required
def fiche_rituel_pdf(id):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    sheet = scoped_query(RitualSheet).get_or_404(id)
    settings = scoped_query(SchoolSettings).first()
    items = sheet.items()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.4*cm, rightMargin=1.4*cm,
                            topMargin=1*cm, bottomMargin=1*cm)
    styles = getSampleStyleSheet()
    title_s = ParagraphStyle('t', parent=styles['Normal'], fontSize=16, alignment=TA_CENTER,
                             fontName='Helvetica-Bold', textColor=colors.HexColor('#a21caf'), spaceAfter=4)
    h = ParagraphStyle('h', parent=styles['Normal'], fontSize=10, fontName='Helvetica-Bold',
                       textColor=colors.HexColor('#86198f'), spaceBefore=6, spaceAfter=2)
    body = ParagraphStyle('b', parent=styles['Normal'], fontSize=9, leading=12)
    small = ParagraphStyle('sm', parent=styles['Normal'], fontSize=8, leading=11)
    elements = []
    school = settings.school_name if settings else 'École'
    elements.append(Paragraph('FICHE RITUELS — Journée', title_s))
    elements.append(Paragraph(f'{school} — U nengue', ParagraphStyle(
        's', parent=styles['Normal'], fontSize=9, alignment=TA_CENTER, spaceAfter=8)))
    cls = sheet.classroom.name if sheet.classroom else '—'
    level = sheet.classroom.level if sheet.classroom else ''
    meta = [[
        Paragraph(f'<b>Classe :</b> {cls} {("(" + level + ")") if level else ""}', body),
        Paragraph(f'<b>Date :</b> {sheet.date.strftime("%d/%m/%Y") if sheet.date else "—"}', body),
        Paragraph(f'<b>Nombre de rituels :</b> {len(items)}', body),
    ]]
    mt = Table(meta, colWidths=[6*cm, 5*cm, 5*cm])
    mt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#fdf4ff')),
        ('BOX', (0, 0), (-1, -1), 1.5, colors.HexColor('#c026d3')),
        ('INNERGRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#e879f9')),
        ('TOPPADDING', (0, 0), (-1, -1), 8),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 8),
    ]))
    elements.append(mt)
    elements.append(Spacer(1, 5*mm))

    palette = [
        ('#c026d3', '#fdf4ff'),
        ('#7c3aed', '#f5f3ff'),
        ('#db2777', '#fdf2f8'),
        ('#0891b2', '#ecfeff'),
        ('#ea580c', '#fff7ed'),
    ]
    for idx, it in enumerate(items, 1):
        bg_h, bg_b = palette[(idx - 1) % len(palette)]
        block = []
        block.append(Paragraph(
            f'<b>Rituel {idx}</b> — {it.get("title") or "Sans titre"} '
            f'&nbsp;&nbsp;|&nbsp;&nbsp; <b>Temps :</b> {it.get("duration") or "—"}',
            ParagraphStyle('rh', parent=styles['Normal'], fontSize=10, fontName='Helvetica-Bold',
                           textColor=colors.white, spaceBefore=0, spaceAfter=0)))
        head_t = Table([[block[-1]]], colWidths=[17*cm])
        head_t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(bg_h)),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 8),
        ]))
        obj = Paragraph(f'<b>Objectif :</b> {it.get("objective") or "—"}', small)
        roles = Table([[
            Paragraph(f'<b>Rôle de l\'enseignant</b><br/>{it.get("teacher_role") or "—"}', small),
            Paragraph(f'<b>Rôle de l\'élève</b><br/>{it.get("student_role") or "—"}', small),
        ]], colWidths=[8.5*cm, 8.5*cm])
        roles.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(bg_b)),
            ('BOX', (0, 0), (-1, -1), 0.8, colors.HexColor(bg_h)),
            ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor(bg_h)),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 6),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        obj_t = Table([[obj]], colWidths=[17*cm])
        obj_t.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor(bg_b)),
            ('BOX', (0, 0), (-1, -1), 0.6, colors.HexColor(bg_h)),
            ('TOPPADDING', (0, 0), (-1, -1), 5),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 5),
            ('LEFTPADDING', (0, 0), (-1, -1), 6),
        ]))
        elements.append(KeepTogether([head_t, obj_t, roles, Spacer(1, 4*mm)]))

    if sheet.notes:
        elements.append(Paragraph('Notes / observations de la journée', h))
        elements.append(Paragraph(sheet.notes, body))
    elements.append(Spacer(1, 8*mm))
    elements.append(Paragraph('Document généré par U nengue — MM', ParagraphStyle(
        'f', parent=styles['Normal'], fontSize=7, alignment=TA_CENTER, textColor=colors.grey)))
    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=True,
                     download_name=f'rituels_{sheet.date.isoformat() if sheet.date else sheet.id}.pdf')

@app.route('/fiches-preparation')
@login_required
def fiches_preparation():
    rooms = scoped_query(ClassRoom).order_by(ClassRoom.level, ClassRoom.name).all()
    if session.get('role') == 'Enseignant':
        u = User.query.get(session.get('user_id'))
        if u and u.class_id:
            rooms = [r for r in rooms if r.id == u.class_id]
    class_id = request.args.get('class_id', type=int)
    q = scoped_query(PrepSheet).order_by(PrepSheet.created_at.desc())
    if class_id:
        q = q.filter_by(class_id=class_id)
    elif session.get('role') == 'Enseignant':
        u = User.query.get(session.get('user_id'))
        if u and u.class_id:
            q = q.filter_by(class_id=u.class_id)
    sheets = q.limit(100).all()
    return render_template('fiches_preparation.html', sheets=sheets, rooms=rooms, class_id=class_id)

@app.route('/fiches-preparation/nouvelle', methods=['GET', 'POST'])
@app.route('/fiches-preparation/<int:id>/edit', methods=['GET', 'POST'])
@login_required
def fiche_preparation_form(id=None):
    import json
    sheet = scoped_query(PrepSheet).get(id) if id else None
    rooms = scoped_query(ClassRoom).order_by(ClassRoom.level, ClassRoom.name).all()
    if session.get('role') == 'Enseignant':
        u = User.query.get(session.get('user_id'))
        if u and u.class_id:
            rooms = [r for r in rooms if r.id == u.class_id]
    if request.method == 'POST':
        if not sheet:
            sheet = PrepSheet(created_by=session.get('user_id'))
            db.session.add(sheet)
        sheet.class_id = request.form.get('class_id', type=int) or None
        sheet.title = request.form.get('title', '').strip()
        sheet.subject = request.form.get('subject', '').strip()
        sheet.duration = request.form.get('duration', '').strip()
        sheet.teacher = request.form.get('teacher', '').strip()
        sheet.prerequisites = request.form.get('prerequisites', '').strip()
        sheet.competences = request.form.get('competences', '').strip()
        sheet.general_objectives = request.form.get('general_objectives', '').strip()
        sheet.phase_comprehension = request.form.get('phase_comprehension', '').strip()
        sheet.phase_automation = request.form.get('phase_automation', '').strip()
        sheet.phase_reinvestment = request.form.get('phase_reinvestment', '').strip()
        sheet.operational_objective = request.form.get('operational_objective', '').strip()
        sheet.core_competence = request.form.get('core_competence', '').strip()
        sheet.opening = request.form.get('opening', '').strip()
        sheet.scaffolding = request.form.get('scaffolding', '').strip()
        sheet.closing = request.form.get('closing', '').strip()
        sheet.obstacles = request.form.get('obstacles', '').strip()
        sheet.instruction = request.form.get('instruction', '').strip()
        durs = request.form.getlist('row_duration[]')
        tasks = request.form.getlist('row_tasks[]')
        acts = request.form.getlist('row_activity[]')
        mats = request.form.getlist('row_material[]')
        roles = request.form.getlist('row_teacher[]')
        crits = request.form.getlist('row_criteria[]')
        rows = []
        for i in range(len(durs)):
            if not any([(durs[i] if i < len(durs) else '').strip(),
                        (tasks[i] if i < len(tasks) else '').strip(),
                        (acts[i] if i < len(acts) else '').strip()]):
                continue
            rows.append({
                'duration': (durs[i] if i < len(durs) else '').strip(),
                'tasks': (tasks[i] if i < len(tasks) else '').strip(),
                'activity': (acts[i] if i < len(acts) else '').strip(),
                'material': (mats[i] if i < len(mats) else '').strip(),
                'teacher': (roles[i] if i < len(roles) else '').strip(),
                'criteria': (crits[i] if i < len(crits) else '').strip(),
            })
        sheet.rows_json = json.dumps(rows, ensure_ascii=False)
        db.session.commit()
        flash('Fiche de préparation enregistrée.', 'success')
        return redirect(url_for('fiche_preparation_pdf', id=sheet.id))
    rows = sheet.rows() if sheet else [
        {'duration': '', 'tasks': '', 'activity': '', 'material': '', 'teacher': '', 'criteria': ''},
        {'duration': '', 'tasks': '', 'activity': '', 'material': '', 'teacher': '', 'criteria': ''},
        {'duration': '', 'tasks': '', 'activity': '', 'material': '', 'teacher': '', 'criteria': ''},
    ]
    return render_template('fiche_preparation_form.html', sheet=sheet, rooms=rooms, rows=rows)

@app.route('/fiches-preparation/<int:id>/pdf')
@login_required
def fiche_preparation_pdf(id):
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer, KeepTogether
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm, mm
    from reportlab.lib.enums import TA_CENTER, TA_LEFT
    sheet = scoped_query(PrepSheet).get_or_404(id)
    settings = scoped_query(SchoolSettings).first()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=A4, leftMargin=1.2*cm, rightMargin=1.2*cm,
                            topMargin=1*cm, bottomMargin=1*cm)
    styles = getSampleStyleSheet()
    title_s = ParagraphStyle('t', parent=styles['Normal'], fontSize=14, alignment=TA_CENTER,
                             fontName='Helvetica-Bold', textColor=colors.HexColor('#6d28d9'), spaceAfter=6)
    h = ParagraphStyle('h', parent=styles['Normal'], fontSize=9, fontName='Helvetica-Bold',
                       textColor=colors.HexColor('#5b21b6'), spaceBefore=5, spaceAfter=2)
    body = ParagraphStyle('b', parent=styles['Normal'], fontSize=8, leading=10)
    cell = ParagraphStyle('c', parent=styles['Normal'], fontSize=7, leading=9)
    elements = []
    school = settings.school_name if settings else 'École'
    elements.append(Paragraph('FICHE DE PRÉPARATION', title_s))
    elements.append(Paragraph(f'{school} — U nengue — {sheet.subject or ""}', ParagraphStyle(
        's', parent=styles['Normal'], fontSize=8, alignment=TA_CENTER, spaceAfter=6)))
    cls = sheet.classroom.name if sheet.classroom else '—'
    head = [[
        Paragraph(f'<b>Titre :</b> {sheet.title or "—"}', body),
        Paragraph(f'<b>Classe :</b> {cls}', body),
        Paragraph(f'<b>Durée :</b> {sheet.duration or "—"}', body),
    ]]
    ht = Table(head, colWidths=[8*cm, 4.5*cm, 4*cm])
    ht.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#f5f3ff')),
        ('BOX', (0, 0), (-1, -1), 1.2, colors.HexColor('#7c3aed')),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(ht)
    elements.append(Spacer(1, 3*mm))
    for label, val in [
        ('Prérequis', sheet.prerequisites),
        ('Compétence(s) travaillée(s)', sheet.competences),
        ('Objectifs généraux à atteindre', sheet.general_objectives),
    ]:
        elements.append(Paragraph(f'<b>{label} :</b> {val or "—"}', body))
    elements.append(Spacer(1, 2*mm))
    phases = [
        [Paragraph('<b>1. Phase de compréhension</b>', cell),
         Paragraph(sheet.phase_comprehension or '—', cell)],
        [Paragraph('<b>2. Phase d\'automatisation</b>', cell),
         Paragraph(sheet.phase_automation or '—', cell)],
        [Paragraph('<b>3. Phase de réinvestissement</b>', cell),
         Paragraph(sheet.phase_reinvestment or '—', cell)],
    ]
    pt = Table(phases, colWidths=[4.5*cm, 12*cm])
    pt.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (0, 0), colors.HexColor('#c4b5fd')),
        ('BACKGROUND', (0, 1), (0, 1), colors.HexColor('#a5b4fc')),
        ('BACKGROUND', (0, 2), (0, 2), colors.HexColor('#67e8f9')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#6d28d9')),
        ('INNERGRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#a78bfa')),
        ('VALIGN', (0, 0), (-1, -1), 'TOP'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(pt)
    elements.append(Spacer(1, 3*mm))
    elements.append(Paragraph('<b>Pour chaque séance</b>', h))
    seance = [
        [Paragraph(f'<b>Objectif opérationnel :</b> {sheet.operational_objective or "—"}', body)],
        [Paragraph(f'<b>Compétence cœur de cible :</b> {sheet.core_competence or "—"}', body)],
        [Paragraph(f'<b>Ouverture :</b> {sheet.opening or "—"}', body)],
        [Paragraph(f'<b>Étayage :</b> {sheet.scaffolding or "—"}', body)],
        [Paragraph(f'<b>Clôture :</b> {sheet.closing or "—"}', body)],
        [Paragraph(f'<b>Obstacles :</b> {sheet.obstacles or "—"}', body)],
    ]
    st = Table(seance, colWidths=[16.5*cm])
    st.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, -1), colors.HexColor('#faf5ff')),
        ('BOX', (0, 0), (-1, -1), 1, colors.HexColor('#c026d3')),
        ('TOPPADDING', (0, 0), (-1, -1), 3),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
    ]))
    elements.append(st)
    if sheet.instruction:
        elements.append(Paragraph(f'<b>CONSIGNE :</b> {sheet.instruction}', body))
    elements.append(Spacer(1, 3*mm))
    rows = sheet.rows()
    if rows:
        data = [[
            Paragraph('<b>Durée</b>', cell),
            Paragraph('<b>Tâches élèves / modalités</b>', cell),
            Paragraph('<b>Activité élève</b>', cell),
            Paragraph('<b>Matériel</b>', cell),
            Paragraph('<b>Rôle enseignant / différenciation</b>', cell),
            Paragraph('<b>Critères de réussite</b>', cell),
        ]]
        for r in rows:
            data.append([
                Paragraph(r.get('duration') or '—', cell),
                Paragraph(r.get('tasks') or '—', cell),
                Paragraph(r.get('activity') or '—', cell),
                Paragraph(r.get('material') or '—', cell),
                Paragraph(r.get('teacher') or '—', cell),
                Paragraph(r.get('criteria') or '—', cell),
            ])
        tbl = Table(data, colWidths=[2*cm, 3.2*cm, 2.8*cm, 2.5*cm, 3.5*cm, 2.5*cm])
        tbl.setStyle(TableStyle([
            ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#7c3aed')),
            ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
            ('BACKGROUND', (0, 1), (-1, -1), colors.HexColor('#faf5ff')),
            ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#8b5cf6')),
            ('VALIGN', (0, 0), (-1, -1), 'TOP'),
            ('TOPPADDING', (0, 0), (-1, -1), 3),
            ('BOTTOMPADDING', (0, 0), (-1, -1), 3),
            ('ROWBACKGROUNDS', (0, 1), (-1, -1),
             [colors.HexColor('#faf5ff'), colors.HexColor('#fdf4ff')]),
        ]))
        elements.append(tbl)
    elements.append(Spacer(1, 6*mm))
    elements.append(Paragraph(
        f'{sheet.teacher or ""} — U nengue — MM',
        ParagraphStyle('f', parent=styles['Normal'], fontSize=7, alignment=TA_CENTER,
                       textColor=colors.grey)))
    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=True,
                     download_name=f'preparation_{sheet.id}.pdf')

@app.route('/guide-postgresql')
@login_required
def guide_postgresql():
    if session.get('role') != 'Directeur':
        flash('Réservé au directeur.', 'danger')
        return redirect(url_for('dashboard'))
    return render_template('guide_postgresql.html')



@app.route('/admin/sauvegarde')
@login_required
def backup_json():
    """Sauvegarde JSON (élèves, classes, paramètres)."""
    if session.get('role') != 'Directeur':
        flash('Réservé au directeur.', 'danger')
        return redirect(url_for('dashboard'))
    import json
    data = {
        'version': 1,
        'exported_at': datetime.utcnow().isoformat() + 'Z',
        'settings': {},
        'classes': [],
        'students': [],
    }
    s = scoped_query(SchoolSettings).first()
    if s:
        data['settings'] = {
            'school_name': s.school_name, 'address': s.address, 'phone': s.phone,
            'email': s.email, 'province': s.province, 'circonscription': s.circonscription,
            'director_name': s.director_name, 'annee_scolaire': s.annee_scolaire,
        }
    for c in scoped_query(ClassRoom).all():
        data['classes'].append({
            'id': c.id, 'name': c.name, 'level': c.level, 'teacher': c.teacher or '',
        })
    for st in scoped_query(Student).all():
        data['students'].append({
            'matricule': st.matricule, 'last_name': st.last_name, 'first_name': st.first_name,
            'birth_date': st.birth_date.isoformat() if st.birth_date else None,
            'birth_place': st.birth_place or '', 'gender': st.gender or '',
            'nationality': st.nationality or '', 'class_name': st.classroom.name if st.classroom else '',
            'class_level': st.classroom.level if st.classroom else '',
            'parent_name': st.parent_name or '', 'parent_phone': st.parent_phone or '',
            'parent_pin': getattr(st, 'parent_pin', '') or '',
            'status': st.status or '', 'address': st.address or '',
            'cep_selected': bool(getattr(st, 'cep_selected', False)),
        })
    buf = io.BytesIO(json.dumps(data, ensure_ascii=False, indent=2).encode('utf-8'))
    fname = f"sauvegarde_u_nengue_{datetime.utcnow().strftime('%Y%m%d_%H%M')}.json"
    return send_file(buf, mimetype='application/json', as_attachment=True, download_name=fname)

@app.route('/admin/restauration', methods=['GET', 'POST'])
@login_required
def restore_json():
    if session.get('role') != 'Directeur':
        flash('Réservé au directeur.', 'danger')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        import json
        f = request.files.get('backup')
        if not f or not f.filename:
            flash('Choisissez un fichier JSON de sauvegarde.', 'danger')
            return redirect(url_for('restore_json'))
        try:
            data = json.loads(f.read().decode('utf-8'))
        except Exception as e:
            flash(f'Fichier invalide : {e}', 'danger')
            return redirect(url_for('restore_json'))
        # Classes
        class_map = {}  # name -> id
        for c in data.get('classes') or []:
            room = scoped_query(ClassRoom).filter_by(name=c.get('name')).first()
            if not room:
                room = ClassRoom(name=c.get('name') or 'Classe', level=c.get('level') or '',
                                 teacher=c.get('teacher') or '')
                db.session.add(room)
                db.session.flush()
            else:
                room.level = c.get('level') or room.level
                room.teacher = c.get('teacher') or room.teacher
            class_map[room.name] = room.id
        # Students
        n_new = n_upd = 0
        for st in data.get('students') or []:
            mat = (st.get('matricule') or '').strip()
            student = scoped_query(Student).filter_by(matricule=mat).first() if mat else None
            if not student:
                student = Student(matricule=mat or None)
                db.session.add(student)
                n_new += 1
            else:
                n_upd += 1
            student.last_name = st.get('last_name') or student.last_name or ''
            student.first_name = st.get('first_name') or student.first_name or ''
            bd = st.get('birth_date')
            if bd:
                try:
                    student.birth_date = datetime.strptime(bd[:10], '%Y-%m-%d').date()
                except Exception:
                    pass
            student.birth_place = st.get('birth_place') or ''
            student.gender = st.get('gender') or ''
            student.nationality = st.get('nationality') or 'Gabonaise'
            student.parent_name = st.get('parent_name') or ''
            student.parent_phone = st.get('parent_phone') or ''
            student.parent_pin = st.get('parent_pin') or ''
            student.status = st.get('status') or 'Nouveau'
            student.address = st.get('address') or ''
            student.cep_selected = bool(st.get('cep_selected'))
            cn = st.get('class_name')
            if cn and cn in class_map:
                student.class_id = class_map[cn]
            elif cn:
                room = scoped_query(ClassRoom).filter_by(name=cn).first()
                if room:
                    student.class_id = room.id
        # Settings
        sett = data.get('settings') or {}
        if sett:
            s = scoped_query(SchoolSettings).first()
            if not s:
                s = SchoolSettings()
                db.session.add(s)
            for k, v in sett.items():
                if hasattr(s, k) and v is not None:
                    setattr(s, k, v)
        db.session.commit()
        flash(f'Restauration terminée : {n_new} élève(s) créé(s), {n_upd} mis à jour.', 'success')
        return redirect(url_for('eleves'))
    return render_template('restauration.html')

@app.route('/eleves/pdf')
@login_required
def eleves_pdf():
    from reportlab.lib.pagesizes import A4, landscape
    from reportlab.lib import colors
    from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph, Spacer
    from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
    from reportlab.lib.units import cm
    from reportlab.lib.enums import TA_CENTER
    q = request.args.get('q', '')
    class_filter = request.args.get('class_id', '')
    level_filter = request.args.get('level', '')
    query = scoped_query(Student)
    tc = teacher_class_filter()
    if tc:
        query = query.filter_by(class_id=tc)
    if q:
        query = query.filter(db.or_(
            Student.last_name.ilike(f'%{q}%'), Student.first_name.ilike(f'%{q}%'),
            Student.matricule.ilike(f'%{q}%')))
    if class_filter and not tc:
        try:
            query = query.filter_by(class_id=int(class_filter))
        except Exception:
            pass
    if level_filter and not tc:
        query = query.join(ClassRoom).filter(ClassRoom.level == level_filter)
    students = query.order_by(Student.last_name).all()
    settings = scoped_query(SchoolSettings).first()
    buffer = io.BytesIO()
    doc = SimpleDocTemplate(buffer, pagesize=landscape(A4),
                            leftMargin=1*cm, rightMargin=1*cm, topMargin=1*cm, bottomMargin=1*cm)
    styles = getSampleStyleSheet()
    title = ParagraphStyle('t', parent=styles['Normal'], fontSize=14, alignment=TA_CENTER,
                           fontName='Helvetica-Bold', textColor=colors.HexColor('#a21caf'), spaceAfter=8)
    cell = ParagraphStyle('c', parent=styles['Normal'], fontSize=8, leading=10)
    elements = []
    school = settings.school_name if settings else 'École'
    elements.append(Paragraph(f'Liste des élèves — {school}', title))
    elements.append(Paragraph(f'U nengue — {datetime.utcnow().strftime("%d/%m/%Y")} — {len(students)} élève(s)',
                              ParagraphStyle('s', parent=styles['Normal'], fontSize=9, alignment=TA_CENTER, spaceAfter=8)))
    data = [[Paragraph(f'<b>{h}</b>', cell) for h in
             ['N°', 'Matricule', 'Nom', 'Prénom', 'Classe', 'Né(e) le', 'Lieu', 'Statut']]]
    for i, s in enumerate(students, 1):
        data.append([
            Paragraph(str(i), cell),
            Paragraph(s.matricule or '—', cell),
            Paragraph(s.last_name or '', cell),
            Paragraph(s.first_name or '', cell),
            Paragraph(s.classroom.name if s.classroom else '—', cell),
            Paragraph(s.birth_date.strftime('%d/%m/%Y') if s.birth_date else '—', cell),
            Paragraph(s.birth_place or '—', cell),
            Paragraph(s.status or '—', cell),
        ])
    t = Table(data, colWidths=[1.2*cm, 3*cm, 3.5*cm, 3.2*cm, 3.5*cm, 2.5*cm, 3.5*cm, 2.5*cm])
    t.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#c026d3')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTNAME', (0, 0), (-1, 0), 'Helvetica-Bold'),
        ('GRID', (0, 0), (-1, -1), 0.4, colors.HexColor('#e879f9')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1),
         [colors.white, colors.HexColor('#fdf4ff')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 4),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 4),
    ]))
    elements.append(t)
    elements.append(Spacer(1, 8))
    elements.append(Paragraph('Document généré par U nengue — MM',
                              ParagraphStyle('f', parent=styles['Normal'], fontSize=7,
                                             alignment=TA_CENTER, textColor=colors.grey)))
    doc.build(elements)
    buffer.seek(0)
    return send_file(buffer, mimetype='application/pdf', as_attachment=True,
                     download_name='liste_eleves.pdf')


# ==================== THEMES ====================

THEMES = [
    ('fuchsia', 'Fuchsia Gabon'),
    ('maternelle-pastel', 'Maternelle pastel'),
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
        settings = scoped_query(SchoolSettings).first()
        if user.email and settings and getattr(settings, 'smtp_enabled', False):
            ok, msg = send_email(
                user.email,
                'U nengue — Code de réinitialisation',
                f'Bonjour {user.full_name},\n\n'
                f'Votre code de réinitialisation est : {code}\n\n'
                f'Utilisez ce code une seule fois sur la page Mot de passe oublié.\n'
                f'Si vous n\'êtes pas à l\'origine de cette demande, ignorez ce message.\n\n'
                f'— U nengue',
                settings
            )
            if ok:
                flash(f'Un code a été envoyé à {user.email}.', 'success')
            else:
                flash(f'E-mail non envoyé ({msg}). Code à communiquer : {code}', 'warning')
        else:
            flash(f'Code de réinitialisation pour {user.full_name} : {code}. '
                  f'(Pour envoi auto : activez SMTP dans Paramètres et renseignez l\'e-mail du compte.)', 'info')
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
    items = scoped_query(Publication).order_by(Publication.created_at.desc()).all()
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

@app.route('/actualites/<int:id>/supprimer', methods=['GET', 'POST'])
@director_required
def actualite_supprimer(id):
    pub = scoped_query(Publication).get_or_404(id)
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
            rooms = scoped_query(ClassRoom).filter_by(id=tc).all()
        else:
            rooms = scoped_query(ClassRoom).order_by(ClassRoom.level).all()
        room = scoped_query(ClassRoom).get(class_id) if class_id else None
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
    room = scoped_query(ClassRoom).get(class_id) if class_id else None
    stats = compute_class_stats(class_id)
    settings = scoped_query(SchoolSettings).first()
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
    books = scoped_query(Textbook).order_by(Textbook.discipline).all()
    return render_template('manuels.html', books=books)

@app.route('/manuels/<int:id>/supprimer', methods=['GET', 'POST'])
@director_required
def manuels_supprimer(id):
    b = scoped_query(Textbook).get_or_404(id)
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
        admin = User.query.filter_by(username='admin').first()
        force_pwd = os.environ.get('FORCE_ADMIN_PASSWORD', 'admin123')
        if not admin:
            db.session.add(User(
                username='admin',
                password_hash=generate_password_hash(force_pwd),
                full_name='Directeur(trice)',
                role='Directeur'
            ))
        elif os.environ.get('RESET_ADMIN', '1') == '1':
            admin.password_hash = generate_password_hash(force_pwd)
            admin.role = 'Directeur'
        if not scoped_query(SchoolSettings).first():
            db.session.add(SchoolSettings(
                school_name='École Publique Primaire',
                province='Estuaire',
                circonscription='Libreville',
                director_name='M./Mme le Directeur',
                annee_scolaire='2025-2026'
            ))
        if scoped_query(ClassRoom).count() == 0:
            for n in NIVEAUX:
                db.session.add(ClassRoom(name=f"{n} A", level=n, teacher=''))
                db.session.add(ClassRoom(name=f"{n} B", level=n, teacher=''))
        db.session.commit()
        if scoped_query(Student).count() == 0:
            c3 = scoped_query(ClassRoom).filter_by(level='3ème année').first()
            c5 = scoped_query(ClassRoom).filter_by(level='5ème année').first()
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


# ========== ACCES CREATEUR (routes de secours) ==========
@app.route('/createur/', methods=['GET', 'POST', 'HEAD', 'OPTIONS'])
@app.route('/panneau-createur', methods=['GET', 'POST', 'HEAD', 'OPTIONS'])
@app.route('/panneau-createur/', methods=['GET', 'POST', 'HEAD', 'OPTIONS'])
def createur_panel_alias():
    """Alias du panneau créateur (évite les 405 selon les navigateurs)."""
    if 'user_id' not in session:
        flash('Veuillez vous connecter avec le compte createur.', 'warning')
        return redirect(url_for('login'))
    creator_name = os.environ.get('CREATOR_USERNAME', 'createur')
    is_c = bool(
        session.get('is_creator')
        or session.get('role') == 'Createur'
        or (session.get('username') or '').lower() == creator_name.lower()
    )
    if not is_c:
        flash('Accès réservé au créateur (identifiant : createur).', 'danger')
        return redirect(url_for('dashboard'))
    session['is_creator'] = True
    try:
        tenants = Tenant.query.order_by(Tenant.created_at.desc()).all()
    except Exception:
        tenants = []
    try:
        users = User.query.filter((User.is_creator == False) | (User.is_creator.is_(None))).order_by(User.username).all()
    except Exception:
        users = User.query.all()
    by_tenant = {}
    for u in users:
        by_tenant.setdefault(getattr(u, 'tenant_id', None), []).append(u)
# --- Tableau de bord créateur (stats dynamiques) ---
    stats = {
        'nb_ecoles': len(tenants),
        'nb_users': len(users),
        'nb_directeurs': sum(1 for u in users if (u.role or '') == 'Directeur'),
        'nb_enseignants': sum(1 for u in users if (u.role or '') == 'Enseignant'),
        'nb_eleves_total': 0,
        'nb_classes_total': 0,
        'par_ecole': [],
    }
    try:
        stats['nb_eleves_total'] = Student.query.count()
        stats['nb_classes_total'] = ClassRoom.query.count()
    except Exception:
        pass
    for t in tenants:
        try:
            n_el = Student.query.filter_by(tenant_id=t.id).count()
            n_cl = ClassRoom.query.filter_by(tenant_id=t.id).count()
            n_us = len(by_tenant.get(t.id, []))
        except Exception:
            n_el = n_cl = n_us = 0
        stats['par_ecole'].append({
            'id': t.id,
            'nom': t.school_name,
            'province': t.province or '',
            'eleves': n_el,
            'classes': n_cl,
            'users': n_us,
        })
    total_el = stats['nb_eleves_total'] or 1
    for pe in stats['par_ecole']:
        pe['pct_eleves'] = round(100.0 * pe['eleves'] / total_el, 1) if stats['nb_eleves_total'] else 0
    if stats['nb_users']:
        stats['pct_directeurs'] = round(100.0 * stats['nb_directeurs'] / stats['nb_users'], 1)
        stats['pct_enseignants'] = round(100.0 * stats['nb_enseignants'] / stats['nb_users'], 1)
    else:
        stats['pct_directeurs'] = stats['pct_enseignants'] = 0
    return render_template('createur_panel.html', tenants=tenants, by_tenant=by_tenant, users=users, stats=stats)


@app.route('/createur', methods=['GET', 'POST', 'HEAD', 'OPTIONS'])
def createur_panel_safe():
    return createur_panel_alias()




@app.route('/panneau-createur/nouvelle-ecole', methods=['GET', 'POST'])
@app.route('/createur/nouvelle-ecole', methods=['GET', 'POST'])
def createur_nouvelle_ecole():
    """Le créateur inscrit une école et son directeur (base vide)."""
    creator_name = os.environ.get('CREATOR_USERNAME', 'createur')
    if 'user_id' not in session:
        flash('Connexion requise.', 'warning')
        return redirect(url_for('login'))
    is_c = bool(session.get('is_creator') or session.get('role') == 'Createur'
                or (session.get('username') or '').lower() == creator_name.lower())
    if not is_c:
        flash('Réservé au créateur.', 'danger')
        return redirect(url_for('dashboard'))
    if request.method == 'POST':
        school_name = (request.form.get('school_name') or '').strip()
        full_name = (request.form.get('full_name') or '').strip()
        username = (request.form.get('username') or '').strip().lower()
        password = request.form.get('password') or ''
        email = (request.form.get('email') or '').strip()
        phone = (request.form.get('phone') or '').strip()
        province = (request.form.get('province') or '').strip()
        role = (request.form.get('role') or 'Directeur').strip()
        if not school_name or not full_name or not username or not password:
            flash('Champs obligatoires manquants.', 'danger')
            return redirect(url_for('createur_nouvelle_ecole'))
        if len(password) < 6:
            flash('Mot de passe : 6 caractères minimum.', 'danger')
            return redirect(url_for('createur_nouvelle_ecole'))
        if User.query.filter_by(username=username).first():
            flash('Identifiant déjà utilisé.', 'danger')
            return redirect(url_for('createur_nouvelle_ecole'))
        if username in ('createur', 'admin') or username == creator_name.lower():
            flash('Identifiant réservé.', 'danger')
            return redirect(url_for('createur_nouvelle_ecole'))
        tenant = Tenant(school_name=school_name, contact_email=email, contact_phone=phone, province=province, is_active=True)
        db.session.add(tenant)
        db.session.flush()
        user = User(
            username=username,
            password_hash=generate_password_hash(password),
            password_plain=password,
            full_name=full_name,
            email=email,
            role=role if role in ('Directeur', 'Enseignant') else 'Directeur',
            is_creator=False,
            tenant_id=tenant.id,
        )
        db.session.add(user)
        db.session.add(SchoolSettings(
            school_name=school_name, annee_scolaire='2025-2026',
            director_name=full_name if role == 'Directeur' else '',
            phone=phone, email=email, province=province, tenant_id=tenant.id,
        ))
        db.session.commit()
        flash(f'École « {school_name} » créée. Identifiant : {username} — base vide prête.', 'success')
        return redirect(url_for('createur_panel_alias'))
    return render_template('createur_nouvelle_ecole.html')


@app.route('/panneau-createur/utilisateur', methods=['GET', 'POST'])
def createur_ajout_utilisateur():
    """Ajouter un utilisateur (directeur ou enseignant) à une école existante."""
    creator_name = os.environ.get('CREATOR_USERNAME', 'createur')
    if 'user_id' not in session:
        return redirect(url_for('login'))
    is_c = bool(session.get('is_creator') or (session.get('username') or '').lower() == creator_name.lower())
    if not is_c:
        flash('Réservé au créateur.', 'danger')
        return redirect(url_for('dashboard'))
    tenants = Tenant.query.order_by(Tenant.school_name).all()
    if request.method == 'POST':
        tid = request.form.get('tenant_id', type=int)
        full_name = (request.form.get('full_name') or '').strip()
        username = (request.form.get('username') or '').strip().lower()
        password = request.form.get('password') or ''
        role = (request.form.get('role') or 'Enseignant').strip()
        email = (request.form.get('email') or '').strip()
        if not tid or not full_name or not username or not password:
            flash('Champs obligatoires manquants.', 'danger')
            return redirect(url_for('createur_ajout_utilisateur'))
        if User.query.filter_by(username=username).first():
            flash('Identifiant déjà pris.', 'danger')
            return redirect(url_for('createur_ajout_utilisateur'))
        u = User(
            username=username,
            password_hash=generate_password_hash(password),
            password_plain=password,
            full_name=full_name,
            email=email,
            role=role if role in ('Directeur', 'Enseignant') else 'Enseignant',
            is_creator=False,
            tenant_id=tid,
        )
        db.session.add(u)
        db.session.commit()
        flash(f'Utilisateur {username} créé pour l\'école sélectionnée.', 'success')
        return redirect(url_for('createur_panel_alias'))
    return render_template('createur_ajout_utilisateur.html', tenants=tenants)




@app.route('/reset-access', methods=['GET', 'POST'])
def reset_access_emergency():
    """Réinitialise admin et createur si la connexion échoue (ex. Render)."""
    try:
        migrate_schema()
        db.create_all()
    except Exception as e:
        print("reset migrate", e)
    key = (request.args.get('key') or request.form.get('key') or '').strip()
    expected = os.environ.get('RESET_KEY', 'u-nengue-reset-2026')
    if request.method == 'GET' and key != expected:
        return (
            '<!doctype html><html><body style="font-family:sans-serif;max-width:420px;margin:3rem auto">'
            '<h2>Réinitialiser l\'accès U nengue</h2>'
            '<form method="post"><p>Clé de sécurité :</p>'
            '<input name="key" style="width:100%;padding:0.5rem" placeholder="u-nengue-reset-2026"/>'
            '<button style="margin-top:1rem;padding:0.6rem 1rem">Réinitialiser admin + createur</button>'
            '</form></body></html>'
        )
    if key != expected:
        flash('Clé incorrecte.', 'danger')
        return redirect(url_for('login'))
    try:
        creator_user = os.environ.get('CREATOR_USERNAME', 'createur')
        creator_pwd = os.environ.get('CREATOR_PASSWORD', 'U-nengue-Createur-2026!')
        force_pwd = os.environ.get('FORCE_ADMIN_PASSWORD', 'admin123')
        c = User.query.filter_by(username=creator_user).first()
        if not c:
            c = User(username=creator_user, full_name='Créateur U nengue', role='Createur', is_creator=True, tenant_id=None)
            db.session.add(c)
        c.password_hash = generate_password_hash(creator_pwd)
        c.password_plain = creator_pwd
        c.is_creator = True
        c.role = 'Createur'
        t = Tenant.query.first()
        if not t:
            t = Tenant(school_name='École Publique Primaire (démo)', province='')
            db.session.add(t)
            db.session.flush()
        a = User.query.filter_by(username='admin').first()
        if not a:
            a = User(username='admin', full_name='Directeur(trice)', role='Directeur', is_creator=False, tenant_id=t.id)
            db.session.add(a)
        a.password_hash = generate_password_hash(force_pwd)
        a.password_plain = force_pwd
        a.role = 'Directeur'
        a.is_creator = False
        if not a.tenant_id:
            a.tenant_id = t.id
        db.session.commit()
        flash('Comptes réinitialisés : createur / U-nengue-Createur-2026!  et  admin / admin123', 'success')
    except Exception as e:
        try:
            db.session.rollback()
        except Exception:
            pass
        flash('Erreur reset : ' + str(e), 'danger')
    return redirect(url_for('login'))



if __name__ == '__main__':
    debug = os.environ.get('FLASK_DEBUG', '0') == '1'
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)), debug=debug)

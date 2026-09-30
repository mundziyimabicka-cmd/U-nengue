from app import app, db, User, SchoolSettings
from werkzeug.security import generate_password_hash

with app.app_context():
    db.create_all()
    if not User.query.filter_by(username='admin').first():
        db.session.add(User(
            username='admin',
            password_hash=generate_password_hash('admin123'),
            full_name='Directeur',
            role='Directeur'
        ))
    if not SchoolSettings.query.first():
        db.session.add(SchoolSettings(school_name='Ecole Primaire'))
    db.session.commit()
    print('Base OK')

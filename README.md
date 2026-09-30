# Kyaf Edu Gabon — École Primaire

Logiciel de gestion pour l'école primaire gabonaise (1ère à 5ème année).
Système d'évaluation par compétences (APC) conforme au bulletin officiel.

## Fonctionnalités

- Inscription élèves avec lieu de naissance, photo (fichier ou webcam), documents
- Fiche individuelle de renseignement avec photo
- Classes : 1ère, 2ème, 3ème, 4ème, 5ème année
- Listes nominatives (tous / par classe)
- Évaluations par compétences (EDM&EAS, Français, Maths) et paliers
- Bulletins PDF conformes (notes critères, maîtrise compétence/matière/palier)
- Cartes scolaires individuelles et collectives
- Sélection CEP pour les élèves de 5ème année
- Interface colorée et dynamique

## Installation

```bash
pip install flask flask-sqlalchemy reportlab Pillow
python app.py
```

Ouvrir http://127.0.0.1:5000
Identifiant : admin / Mot de passe : admin123

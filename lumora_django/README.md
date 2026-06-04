# LUMØRA — Django

## Installation locale

```bash
python -m venv venv
source venv/bin/activate        # Windows: venv\Scripts\activate
pip install -r requirements.txt
cp .env.example .env            # puis éditez .env
python manage.py migrate
python manage.py createsuperuser
python manage.py runserver
```

Site : http://127.0.0.1:8000  
Admin : http://127.0.0.1:8000/admin

## Déploiement Infomaniak (Cloud Server)

```bash
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
gunicorn lumora_project.wsgi:application --bind 0.0.0.0:8000
```

Configurer Nginx comme reverse proxy vers le port 8000.

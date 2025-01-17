release: python manage.py migrate --no-input
web: gunicorn llm_wars.wsgi
worker: bash run.sh
scheduler: python manage.py scheduler

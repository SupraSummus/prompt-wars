postdeploy: python manage.py migrate --no-input
web: gunicorn llm_wars.wsgi
worker: python manage.py goals_threaded_worker --threads 4
scheduler: python manage.py scheduler

release: python manage.py migrate --no-input
web: gunicorn llm_wars.wsgi
worker: python manage.py q_cluster

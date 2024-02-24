release: python manage.py migrate --no-input
web: trap '' SIGTERM; gunicorn llm_wars.wsgi & python manage.py qcluster & wait -n; kill -SIGTERM -$$; wait

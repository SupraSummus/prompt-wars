trap '' SIGTERM

gunicorn llm_wars.wsgi &
python manage.py qcluster &
python manage.py scheduler &

wait -n

kill -SIGTERM -$$
wait

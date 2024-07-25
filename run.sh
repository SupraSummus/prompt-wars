trap '' SIGTERM

gunicorn llm_wars.wsgi &
python manage.py goals_busy_worker &
python manage.py scheduler &

wait -n

kill -SIGTERM -$$
wait

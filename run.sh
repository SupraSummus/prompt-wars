trap '' SIGTERM

gunicorn llm_wars.wsgi --max-requests 100 --max-requests-jitter 10 &
(yes | xargs -I -L1 -P1 -- python manage.py goals_busy_worker --max-progress-count 10) &
python manage.py scheduler &

wait -n

kill -SIGTERM -$$
wait

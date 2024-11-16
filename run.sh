# Heroku's dyno manager sends SIGTERM to all processes in the dyno (not just the root process)
# We ignore it in root process
trap '' SIGTERM

gunicorn llm_wars.wsgi --max-requests 100 --max-requests-jitter 10 &
(
    trap 'exit' SIGTERM
    while true; do
        python manage.py goals_busy_worker --max-progress-count 10
    done
) &
python manage.py scheduler &

# Wait for any child processes to exit
wait -n

# We send SIGTERM to all processes in the process group, not just the root process
kill -SIGTERM -$$
wait

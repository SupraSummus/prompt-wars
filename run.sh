# Heroku's dyno manager sends SIGTERM to all processes in the dyno (not just the root process)
trap 'exit' SIGTERM
while true; do
    python manage.py goals_busy_worker --max-progress-count 10
done

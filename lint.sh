set -e

flake8
pylint .
python manage.py makemigrations --check

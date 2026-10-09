from datetime import timedelta

from django_scheduler.models import register_job

from .handover import hill_handover
from .status import sweep_hill_attempts


register_job(sweep_hill_attempts, timedelta(minutes=1), key='hill_sweep')
register_job(hill_handover, timedelta(minutes=1), key='hill_handover')

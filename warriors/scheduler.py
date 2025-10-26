from datetime import timedelta

from django_scheduler.models import register_job

from .random_matchmaking import schedule_battle
from .rating_models import update_rating
from .stats import create_arena_stats
from .tasks import schedule_battles_top


register_job(schedule_battle, timedelta(seconds=1))
register_job(schedule_battles_top, timedelta(minutes=10))
register_job(update_rating, timedelta(seconds=1))
register_job(create_arena_stats, timedelta(hours=1))

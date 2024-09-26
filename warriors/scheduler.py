import logging
import sched

from .stats import create_arena_stats
from .tasks import schedule_battle, schedule_battles_top, update_rating


logger = logging.getLogger(__name__)


class Scheduler(sched.scheduler):
    def enter_recurring(self, delay, priority, action, argument=(), kwargs={}):
        action(*argument, **kwargs)
        self.enter(delay, priority, self.enter_recurring, (delay, priority, action, argument, kwargs))

    def run(self, *args, **kwargs):
        logger.info('Starting scheduler')
        return super().run(*args, **kwargs)

    def clear(self):
        logger.info('Clearing scheduler')
        with self._lock:
            self._queue.clear()


scheduler = Scheduler()
scheduler.enter_recurring(1, 0, schedule_battle)
scheduler.enter_recurring(60 * 10, 0, schedule_battles_top)
scheduler.enter_recurring(60, 0, update_rating)
scheduler.enter_recurring(60 * 60, 0, create_arena_stats)

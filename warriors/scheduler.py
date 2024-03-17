import sched

from .tasks import schedule_battle


class Scheduler(sched.scheduler):
    def enter_recurring(self, delay, priority, action, argument=(), kwargs={}):
        action(*argument, **kwargs)
        self.enter(delay, priority, self.enter_recurring, (delay, priority, action, argument, kwargs))


scheduler = Scheduler()
scheduler.enter_recurring(1, 0, schedule_battle)

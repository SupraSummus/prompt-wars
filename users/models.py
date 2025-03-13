import datetime
import uuid

from django.contrib.auth.models import AbstractUser
from django.core.management import call_command
from django.db import models

from django_scheduler.models import register_job


class User(AbstractUser):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )


register_job(
    lambda now: call_command('clearsessions'),
    interval=datetime.timedelta(days=1),
    key='clearsessions',
)

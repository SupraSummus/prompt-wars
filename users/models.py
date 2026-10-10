import datetime
import uuid

from django.contrib.auth.models import AbstractUser
from django.core.management import call_command
from django.db import models
from django.utils import timezone

from django_scheduler.models import register_job


class User(AbstractUser):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )


class GoogleAccount(models.Model):
    """
    A Google account that logs in as `user` (`users.google_login`).
    It is matched by Google's subject id, never by email:
    an address can move to another Google account,
    and the accounts made with a password have none to match.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    # Google's `sub` claim: at most 255 ASCII characters, case-sensitive
    sub = models.CharField(
        max_length=255,
        unique=True,
    )
    user = models.ForeignKey(
        to=User,
        on_delete=models.CASCADE,
        related_name='google_accounts',
    )
    created_at = models.DateTimeField(
        default=timezone.now,
    )


register_job(
    lambda now: call_command('clearsessions'),
    interval=datetime.timedelta(days=1),
    key='clearsessions',
)

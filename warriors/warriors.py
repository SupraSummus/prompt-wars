import uuid

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _


MAX_WARRIOR_LENGTH = 1000


class WarriorQuerySet(models.QuerySet):
    def battleworthy(self):
        return self.filter(
            moderation_passed=True,
        )


class Warrior(models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    body = models.TextField(
        max_length=MAX_WARRIOR_LENGTH,
    )
    body_sha_256 = models.BinaryField(
        max_length=32,
        unique=True,
    )
    created_at = models.DateTimeField(
        default=timezone.now,
    )
    created_by = models.ForeignKey(
        to=settings.AUTH_USER_MODEL,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
    )
    name = models.CharField(
        max_length=40,
        blank=True,
    )
    author_name = models.CharField(
        max_length=40,
        blank=True,
    )

    moderation_date = models.DateTimeField(
        null=True,
        blank=True,
    )
    moderation_passed = models.BooleanField(
        null=True,
    )
    moderation_model = models.CharField(
        max_length=100,
        blank=True,
    )

    public_battle_results = models.BooleanField(
        default=False,
        help_text=_("Indicates whether battle results should be public for this warrior."),
    )

    def update_public_battle_results(self):
        """Recompute public_battle_results based on per user data"""
        from .models import WarriorUserPermission
        user_permissions = list(WarriorUserPermission.objects.filter(
            warrior_arena__warrior=self,
        ))
        if user_permissions:
            self.public_battle_results = any(
                up.public_battle_results
                for up in user_permissions
            )
            self.save(update_fields=['public_battle_results'])

    users = models.ManyToManyField(
        to=settings.AUTH_USER_MODEL,
        through='WarriorUserPermission',
        related_name='+',  # TODO: change to 'warriors'
    )

    objects = WarriorQuerySet.as_manager()

    class Meta:
        ordering = ('id',)
        constraints = [
            models.CheckConstraint(
                check=models.Q(body_sha_256=models.Func(
                    models.Func(
                        models.F('body'),
                        models.Value('utf-8'),
                        function='convert_to',
                    ),
                    function='sha256',
                )),
                name='warrior_body_sha_256',
            ),
        ]

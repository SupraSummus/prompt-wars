import uuid
from functools import lru_cache

from django.conf import settings
from django.db import models
from django.utils import timezone
from django.utils.translation import gettext_lazy as _
from django_goals.models import AllDone

from .embeddings import EmbeddingMixin, _ensure_voyage_3_embedding


MAX_WARRIOR_LENGTH = 1000


class WarriorQuerySet(models.QuerySet):
    def battleworthy(self):
        return self.filter(
            moderation_passed=True,
        )


class Warrior(EmbeddingMixin, models.Model):
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    body = models.TextField(
        max_length=MAX_WARRIOR_LENGTH,
    )

    @property
    def content(self):
        return self.body

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
            warrior=self,
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

    def __str__(self):
        if self.moderation_passed is not True:
            return str(self.id)
        return self.name or str(self.id)

    @property
    def ensure_voyage_3_embedding_handler(self):
        return ensure_voyage_3_embedding

    @lru_cache(maxsize=16)
    def is_user_authorized(self, user):
        if not user.is_authenticated:
            return False
        return self.users.filter(id=user.id).exists()


def ensure_voyage_3_embedding(goal):
    instance = goal.warrior
    return _ensure_voyage_3_embedding(instance)


def ensure_name_generated(goal, warrior_id):
    warrior = Warrior.objects.get(id=warrior_id)
    if not warrior.name and warrior.moderation_passed:
        generate_warrior_name(warrior)
    return AllDone()


def generate_warrior_name(warrior, samples=20):
    from .openai import call_llm

    # Get 10 random warriors with names and approved moderation
    example_warriors = Warrior.objects.filter(
        moderation_passed=True,
    ).exclude(name='').exclude(id=warrior.id).order_by('?')[:samples]

    # Prepare examples for call_llm
    examples = [(w.body, w.name) for w in example_warriors]

    # Call the language model
    system_prompt = (
        "You are an AI assistant that generates names for warriors in a game called Prompt Wars. "
        "This game is inspired by Core War and involves players crafting text pieces "
        "(warriors/spells/prompts) designed to manipulate large language models (LLMs) into "
        "echoing the original prompt. Your task is to generate a name for each warrior. "
        "The name should fit within a database field "
        "of 40 characters maximum."
    )

    generated_name, model_info = call_llm(
        examples, warrior.body,
        system_prompt=system_prompt,
        max_tokens=100,
    )

    warrior.name = generated_name.strip()[:40]
    warrior.save(update_fields=['name'])

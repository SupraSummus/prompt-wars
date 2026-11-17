import hashlib

import factory
from django.utils import timezone

from users.tests.factories import UserFactory

from ..battles import LLM, Battle, Game
from ..models import WarriorUserPermission
from ..rankings import Ranking
from ..rating_models import WarriorRating, enter_ladder
from ..score import GameScore
from ..text_unit import TextUnit
from ..warriors import Warrior


class WarriorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Warrior
        skip_postgeneration_save = True

    body = factory.Sequence(lambda n: f'factory-made warrior body {n}')
    body_sha_256 = factory.LazyAttribute(
        lambda o: hashlib.sha256(o.body.encode('utf-8')).digest()
    )
    moderation_passed = True
    # on the ladder, as a warrior submitted through the prompt form is;
    # `next_battle_schedule=None` makes one that plays only the hill
    next_battle_schedule = factory.LazyFunction(timezone.now)

    @factory.post_generation
    def ladder(obj, create, extracted, **kwargs):
        """A warrior with a clock has a rating in every ranking, as `enter_ladder` leaves it."""
        if create and obj.next_battle_schedule is not None:
            enter_ladder(obj)


class WarriorRatingFactory(factory.django.DjangoModelFactory):
    """
    A warrior's rating in one ranking, set to the given fields.

    A ladder warrior has its ratings from the start (`WarriorFactory.ladder`),
    so this sets one rather than inserting a second.
    """
    class Meta:
        model = WarriorRating

    ranking = Ranking.LCS
    warrior = factory.SubFactory(WarriorFactory)

    @classmethod
    def _create(cls, model_class, *args, warrior, ranking, **kwargs):
        rating, _ = model_class.objects.update_or_create(
            warrior=warrior,
            ranking=ranking,
            defaults=kwargs,
        )
        return rating


class WarriorUserPermissionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WarriorUserPermission

    warrior = factory.SubFactory(WarriorFactory)
    user = factory.SubFactory(UserFactory)


class GameFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Game

    llm = factory.SelfAttribute('battle.llm')
    scheduled_at = factory.SelfAttribute('battle.scheduled_at')


class BattleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Battle
        skip_postgeneration_save = True

    llm = LLM.OPENAI_GPT
    warrior_1 = factory.SubFactory(WarriorFactory)
    warrior_2 = factory.SubFactory(WarriorFactory)

    @classmethod
    def _adjust_kwargs(cls, **kwargs):
        """
        Put the warrior pair in the battle's canonical order.

        The `warrior_ordering` check constraint wants the smaller id first,
        which a caller building a pair cannot arrange in advance —
        the ids come from the factory.
        The games are built after the swap,
        so `game_1_2` is the one the canonical first warrior leads.

        This rebinds nothing for the caller:
        a test that names its warriors and then asserts per name
        has to sort them itself, or read the order back off the battle.
        """
        if kwargs['warrior_1'].id > kwargs['warrior_2'].id:
            kwargs['warrior_1'], kwargs['warrior_2'] = (
                kwargs['warrior_2'], kwargs['warrior_1'],
            )
        return kwargs

    # Hold the invariant `resolve_battle` relies on:
    # a battle comes with its two game rows.
    # `game_1_2__resolved_at=...` sets a field on one of them.
    game_1_2 = factory.RelatedFactory(
        GameFactory, 'battle',
        warrior_1=factory.SelfAttribute('battle.warrior_1'),
        warrior_2=factory.SelfAttribute('battle.warrior_2'),
    )
    game_2_1 = factory.RelatedFactory(
        GameFactory, 'battle',
        warrior_1=factory.SelfAttribute('battle.warrior_2'),
        warrior_2=factory.SelfAttribute('battle.warrior_1'),
    )


def batch_create_battles(warrior, n):
    """Create n resolved battles between the warrior and new opponents."""
    battles = []
    for _ in range(n):
        battle = BattleFactory(
            warrior_1=warrior,
            warrior_2=WarriorFactory(),
            game_1_2__resolved_at=timezone.now(),
            game_1_2__text_unit=TextUnitFactory(),
            game_2_1__resolved_at=timezone.now(),
            game_2_1__text_unit=TextUnitFactory(),
        )
        battles.append(battle)
    return battles


class TextUnitFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = TextUnit

    content = factory.Sequence(lambda n: f'factory-made text unit body {n}')
    sha_256 = factory.LazyAttribute(
        lambda o: hashlib.sha256(o.content.encode('utf-8')).digest()
    )


def game_of(battle, direction):
    """The game row that plays the battle out in the given direction."""
    return battle.games.get(
        warrior_1_id=(
            battle.warrior_1_id if direction == '1_2'
            else battle.warrior_2_id
        ),
    )


class GameScoreFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = GameScore

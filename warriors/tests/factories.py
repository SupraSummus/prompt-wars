import hashlib

import factory
from django.utils import timezone

from users.tests.factories import UserFactory

from ..battles import Battle, DBGame, mirrored_game_fields
from ..models import LLM, Arena, WarriorArena, WarriorUserPermission
from ..score import GameScore
from ..text_unit import TextUnit
from ..warriors import Warrior


class ArenaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Arena

    name = factory.Sequence(lambda n: f'factory-made arena {n}')
    llm = LLM.OPENAI_GPT


class WarriorFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Warrior

    body = factory.Sequence(lambda n: f'factory-made warrior body {n}')
    body_sha_256 = factory.LazyAttribute(
        lambda o: hashlib.sha256(o.body.encode('utf-8')).digest()
    )
    moderation_passed = True


class WarriorArenaFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WarriorArena

    arena = factory.SubFactory(ArenaFactory)
    warrior = factory.SubFactory(WarriorFactory)


class WarriorUserPermissionFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = WarriorUserPermission

    warrior = factory.SubFactory(WarriorFactory)
    user = factory.SubFactory(UserFactory)


class BattleFactory(factory.django.DjangoModelFactory):
    class Meta:
        model = Battle
        skip_postgeneration_save = True

    warrior_1 = factory.SubFactory(WarriorFactory)
    warrior_2 = factory.SubFactory(WarriorFactory)

    @factory.post_generation
    def games(battle, create, extracted, **kwargs):
        """
        Hold the invariant `resolve_battle` relies on:
        a battle comes with its two game rows,
        mirroring whichever directional fields the caller set.
        """
        if not create:
            return
        for direction in ('1_2', '2_1'):
            DBGame.objects.create(
                battle=battle,
                **mirrored_game_fields(battle, direction),
            )


def batch_create_battles(arena, warrior_arena, n):
    """Create n battles between warrior_arena and new opponents in the same arena."""
    battles = []
    for _ in range(n):
        other_warrior_arena = WarriorArenaFactory(arena=arena)
        battle_warrior_1 = warrior_arena.warrior
        battle_warrior_2 = other_warrior_arena.warrior
        if battle_warrior_1.id > battle_warrior_2.id:
            battle_warrior_1, battle_warrior_2 = battle_warrior_2, battle_warrior_1
        battle = BattleFactory(
            arena=arena,
            llm=arena.llm,
            warrior_1=battle_warrior_1,
            warrior_2=battle_warrior_2,
            resolved_at_1_2=timezone.now(),
            text_unit_1_2=TextUnitFactory(),
            resolved_at_2_1=timezone.now(),
            text_unit_2_1=TextUnitFactory(),
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

    # what get_or_create_game_score writes: the pair and the game row it
    # names, so a test row is shaped like a production one
    game = factory.LazyAttribute(lambda score: game_of(score.battle, score.direction))

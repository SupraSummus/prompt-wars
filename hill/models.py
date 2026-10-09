import uuid

from django.db import connection, models
from django.db.models import Q
from django.utils import timezone
from django.utils.translation import gettext_lazy as _

from warriors.battles import LLM, Battle
from warriors.warriors import Warrior


class Hill(models.Model):
    """
    The owner's switches for King of the Hill, changeable in admin without a deploy.

    A singleton: `Hill.current()` is the hill,
    and with no row, or with `enabled` off, the feature is off.
    The game's rules are constants in `hill.rules`.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    enabled = models.BooleanField(
        default=False,
    )
    # Only the referees that run at temperature 0:
    # the repeat rule and charging a failed battle to its player assume a battle replays.
    llm = models.CharField(
        max_length=20,
        choices=[(llm.value, llm.label) for llm in (LLM.GOOGLE_GEMINI, LLM.CLAUDE_3_HAIKU)],
        default=LLM.GOOGLE_GEMINI,
        help_text=_('Copied into each new round, so a change takes effect at the next handover.'),
    )
    daily_attempt_limit = models.PositiveIntegerField(
        default=1000,
        help_text=_("Attacks per round: the cap on the hill's daily LLM spend."),
    )
    max_pending = models.PositiveSmallIntegerField(
        default=10,
        help_text=_(
            'Attacks being judged at once, across rounds, before new ones are refused. '
            'Lower it to hand the worker back to the ladder during a spike.'
        ),
    )

    def __str__(self):
        return 'King of the Hill'

    @classmethod
    def current(cls):
        return cls.objects.order_by('id').first()


class HouseBoss(models.Model):
    """
    An owner-placed boss the hill falls back to (`hill.handover.next_house_boss`).

    The names live here, typed by the owner,
    because a house boss may wait rounds before it first serves
    and the hill never shows `Warrior.name`.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    hill = models.ForeignKey(
        to=Hill,
        on_delete=models.CASCADE,
        # hill_house_boss_unique leads with hill and answers lookups by it
        db_index=False,
    )
    warrior = models.ForeignKey(
        to=Warrior,
        on_delete=models.PROTECT,
        related_name='+',
    )
    name = models.CharField(
        max_length=40,
        blank=True,
    )
    author = models.CharField(
        max_length=40,
        blank=True,
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('hill', 'warrior'),
                name='hill_house_boss_unique',
            ),
        ]

    def __str__(self):
        return self.name or str(self.warrior_id)


class BossReason(models.TextChoices):
    OWNER = 'owner', _('Crowned by the owner')
    BROKE = 'broke', _('Broke the hill')
    INHERITED = 'inherited', _('Inherited the hill')
    HOUSE = 'house', _('House boss')
    HELD = 'held', _('Held the hill')


class RoundQuerySet(models.QuerySet):
    def open_in(self, hill):
        """The hill's open round, None without a hill or before its first round; with its boss, which every hill page shows."""
        if hill is None:
            return None
        return self.filter(
            hill=hill,
            closed_at=None,
        ).select_related(
            'boss',
            'boss_attempt',
        ).defer(
            # select_related doesn't apply `WarriorManager`'s defer
            'boss__voyage_3_embedding',
        ).first()


class Round(models.Model):
    """
    One numbered window ("Hill #N") with a fixed boss.

    Attacks are accepted while `now < ends_at`;
    the handover closes the round and opens the next one in one transaction.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    hill = models.ForeignKey(
        to=Hill,
        on_delete=models.CASCADE,
        related_name='rounds',
        # hill_round_number_unique leads with hill and answers lookups by it
        db_index=False,
    )
    number = models.PositiveIntegerField()
    starts_at = models.DateTimeField()
    ends_at = models.DateTimeField()
    llm = models.CharField(
        max_length=20,
        choices=LLM.choices,
    )
    boss = models.ForeignKey(
        to=Warrior,
        on_delete=models.PROTECT,
        related_name='+',
    )
    boss_attempt = models.ForeignKey(
        to='HillAttempt',
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name='+',
        help_text=_('The attack that put this boss on the hill; none for owner and house bosses.'),
    )
    # A display snapshot, never `Warrior.name`:
    # generated ladder names are not moderated.
    boss_name = models.CharField(
        max_length=40,
        blank=True,
    )
    boss_author = models.CharField(
        max_length=40,
        blank=True,
    )
    reign_round = models.PositiveSmallIntegerField(
        default=1,
        help_text=_('Consecutive rounds this boss has held, counting this one.'),
    )
    boss_reason = models.CharField(
        max_length=10,
        choices=BossReason.choices,
    )
    closed_at = models.DateTimeField(
        null=True,
        blank=True,
    )

    objects = RoundQuerySet.as_manager()

    class Meta:
        ordering = ('-number',)
        constraints = [
            models.UniqueConstraint(
                fields=('hill', 'number'),
                name='hill_round_number_unique',
            ),
            # the handover's double-run guard, alongside its locks
            models.UniqueConstraint(
                fields=('hill',),
                condition=Q(closed_at=None),
                name='hill_one_open_round',
            ),
        ]

    def __str__(self):
        return f'Hill #{self.number}'

    @property
    def boss_shown(self):
        """Whether pages show the boss's text and names: not once moderation, or the owner's takedown, flags it."""
        return self.boss.moderation_passed is True

    @property
    def shown_name(self):
        return self.boss_name if self.boss_shown else ''

    @property
    def shown_author(self):
        return self.boss_author if self.boss_shown else ''

    @property
    def boss_label(self):
        """The boss's name, or its place, without an article so it can start a sentence."""
        return self.shown_name or f'Hill #{self.number} boss'


class AttemptState(models.TextChoices):
    PENDING = 'pending', _('Pending')
    SCORED = 'scored', _('Scored')
    # the referee returned nothing usable; counts against the player
    FAILED = 'failed', _('Failed')
    FLAGGED = 'flagged', _('Flagged by moderation')
    # lost to infrastructure; refunded
    VOID = 'void', _('Void')


class CrownBlock(models.TextChoices):
    NONE = '', _('None')
    TOO_LITTLE_SURVIVED = 'too_little_survived', _('Too little survived')
    REPETITIVE_REPLY = 'repetitive_reply', _('Repetitive reply')


class HillAttemptQuerySet(models.QuerySet):
    def live(self):
        """Attempts that count against their player's cap: all but the void, which are refunded."""
        return self.exclude(state=AttemptState.VOID)

    def counted(self):
        """Scored attempts that count in their round: not the late ones."""
        return self.filter(state=AttemptState.SCORED, late=False)

    def eligible(self):
        """
        Counted attempts that may take the hill, given the margin (`hill.rules.beats_boss`):
        past the crown gates, and with a spell moderation passed, which a takedown revokes.
        """
        return self.counted().filter(crown_block=CrownBlock.NONE, warrior__moderation_passed=True)


class HillAttempt(models.Model):
    """
    One attack: one spell against its round's boss, fought as one unrated battle.

    The text stays sealed to its author
    unless the attempt becomes a boss.
    """
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    hill_round = models.ForeignKey(
        to=Round,
        on_delete=models.PROTECT,
        related_name='attempts',
        # hill_attempt_round_identity leads with hill_round and answers lookups by it
        db_index=False,
    )
    warrior = models.ForeignKey(
        to=Warrior,
        on_delete=models.PROTECT,
        related_name='hill_attempts',
    )
    # `hill.identity`: the attacker's session key
    identity = models.CharField(
        max_length=64,
    )
    # typed in the hill form, shown to anyone else only on the boss card,
    # once `hill.tasks.moderate_crowned_attempt` passes them
    display_name = models.CharField(
        max_length=40,
        blank=True,
    )
    display_author = models.CharField(
        max_length=40,
        blank=True,
    )
    created_at = models.DateTimeField(
        default=timezone.now,
    )
    state = models.CharField(
        max_length=10,
        choices=AttemptState.choices,
        default=AttemptState.PENDING,
    )
    late = models.BooleanField(
        default=False,
        help_text=_('Still being judged when its round closed: shown to its author, never counted.'),
    )
    battle = models.OneToOneField(
        to=Battle,
        on_delete=models.PROTECT,
        related_name='hill_attempt',
    )
    # written at finalize (`hill.status.finalize_attempt`)
    score = models.FloatField(
        null=True,
        blank=True,
    )
    survived_chars = models.PositiveIntegerField(
        null=True,
        blank=True,
    )
    crown_block = models.CharField(
        max_length=20,
        choices=CrownBlock.choices,
        blank=True,
    )
    output_moderation_passed = models.BooleanField(
        null=True,
        blank=True,
        help_text=_("Moderation of the battle's replies, run once the attempt takes the hill."),
    )

    objects = HillAttemptQuerySet.as_manager()

    class Meta:
        ordering = ('created_at',)
        constraints = [
            models.UniqueConstraint(
                fields=('hill_round', 'warrior'),
                condition=~Q(state='void'),
                name='hill_attempt_live_unique',
            ),
        ]
        indexes = [
            models.Index(
                fields=('hill_round', 'identity'),
                name='hill_attempt_round_identity',
            ),
            # admission counts pending attempts on every attack, and the sweep reads them every minute
            models.Index(
                fields=('created_at',),
                condition=Q(state='pending'),
                name='hill_attempt_pending',
            ),
        ]

    def __str__(self):
        return str(self.id)


class TallyKind(models.TextChoices):
    # counted by `hill.views.shared`
    SHARE_PRESSED = 'share_pressed', _('Share pressed')
    # counted by `hill.views.attack`
    NEW_VIA_SHARE = 'new_via_share', _('New player through a shared link')


class RoundTally(models.Model):
    """A round's count of one `TallyKind`, kept without recording who; `hill_report` reads it."""
    id = models.UUIDField(
        primary_key=True,
        default=uuid.uuid4,
        editable=False,
    )
    hill_round = models.ForeignKey(
        to=Round,
        on_delete=models.CASCADE,
        related_name='tallies',
        # hill_round_tally_unique leads with hill_round and answers lookups by it
        db_index=False,
    )
    kind = models.CharField(
        max_length=20,
        choices=TallyKind.choices,
    )
    count = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=('hill_round', 'kind'),
                name='hill_round_tally_unique',
            ),
        ]

    @classmethod
    def bump(cls, hill_round_id, kind):
        """Count one more `kind` in the round: one upsert, which the ORM can't write, so concurrent bumps never lose a count."""
        with connection.cursor() as cursor:
            cursor.execute(
                f'INSERT INTO {cls._meta.db_table} AS tally (id, hill_round_id, kind, count) VALUES (%s, %s, %s, 1) '
                'ON CONFLICT (hill_round_id, kind) DO UPDATE SET count = tally.count + 1',
                [uuid.uuid4(), hill_round_id, kind],
            )

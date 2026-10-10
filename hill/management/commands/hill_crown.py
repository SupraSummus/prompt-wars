import uuid
from pathlib import Path

from django.core.exceptions import ValidationError
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from hill.forms import NAME_MAX_LENGTH, clean_display_text
from hill.handover import Successor, crown
from hill.models import BossReason, Hill, HouseBoss, Round
from hill.tasks import (
    TRANSIENT_MODERATION_ERRORS, moderate, record_warrior_moderation,
)
from warriors.warriors import (
    Warrior, get_or_insert_warrior, normalize_warrior_body,
)


class Command(BaseCommand):
    """
    The owner's hand on the hill: seed the first boss, replace a boss, or add a house boss.

    The prompt is moderated synchronously before any lock is taken,
    so the scheduler's handover never waits on the moderation call.
    """
    help = (
        'Crown a prompt as the hill boss at once (--now), add it to the house bosses (--house), or both. '
        'Creates the hill, disabled, if there is none.'
    )

    def add_arguments(self, parser):
        source = parser.add_mutually_exclusive_group(required=True)
        source.add_argument(
            '--body-file',
            type=Path,
            help="A file holding the prompt; the file's final line break is not part of it.",
        )
        source.add_argument(
            '--warrior',
            type=uuid.UUID,
            help='The id of an existing warrior.',
        )
        parser.add_argument(
            '--name',
            help='The name the hill shows for this boss; left out, a house boss keeps the one it has.',
        )
        parser.add_argument(
            '--author',
            help='The author the hill shows for this boss; left out, a house boss keeps the one it has.',
        )
        parser.add_argument('--house', action='store_true', help='Add the prompt to the house bosses.')
        parser.add_argument('--now', action='store_true', help='Make the prompt the boss now, closing the open round.')

    def handle(self, *args, **options):
        if not (options['house'] or options['now']):
            raise CommandError('Pass --now to crown the prompt, --house to add it to the house bosses, or both.')
        names = {
            field: self._display_text(options[field], f'--{field}')
            for field in ('name', 'author')
            if options[field] is not None
        }
        if options['body_file'] is not None:
            warrior = self._warrior_from_file(options['body_file'])
        else:
            warrior = Warrior.objects.filter(id=options['warrior']).first()
            if warrior is None:
                raise CommandError(f'No warrior has the id {options["warrior"]}.')
        self._ensure_moderated(warrior)

        with transaction.atomic():
            hill = Hill.current() or Hill.objects.create()
            hill = Hill.objects.select_for_update().get(id=hill.id)
            hill_round = Round.objects.select_for_update().filter(
                hill=hill,
                closed_at=None,
            ).first()
            house_boss = HouseBoss.objects.filter(hill=hill, warrior=warrior).first()
            if options['house']:
                house_boss, _ = HouseBoss.objects.update_or_create(
                    hill=hill,
                    warrior=warrior,
                    defaults=names,
                )
                self.stdout.write(f'Added {warrior.id} to the house bosses of {hill}.')
            if options['now']:
                if house_boss is not None:
                    # crowning a house boss shows its names unless new ones are given
                    names = {'name': house_boss.name, 'author': house_boss.author, **names}
                next_round = crown(hill, hill_round, Successor(
                    warrior=warrior,
                    attempt=None,
                    reason=BossReason.OWNER,
                    reign_round=1,
                    **names,
                ), timezone.now())
                self.stdout.write(f'{next_round} is open with {warrior.id} as its boss, until {next_round.ends_at:%Y-%m-%d %H:%M} UTC.')
        if not hill.enabled:
            self.stdout.write('The hill is disabled; enable it in the admin to open it to attacks.')

    def _display_text(self, text, option):
        text = clean_display_text(text)
        if len(text) > NAME_MAX_LENGTH:
            raise CommandError(f'{option} takes at most {NAME_MAX_LENGTH} characters.')
        return text

    def _warrior_from_file(self, path):
        body = path.read_text(encoding='utf-8')
        if body.endswith('\n'):
            body = body[:-1]
        if not body:
            raise CommandError(f'{path} holds no prompt.')
        try:
            body, body_sha_256 = normalize_warrior_body(body)
        except ValidationError as error:
            raise CommandError(error.messages[0]) from error
        warrior, _ = get_or_insert_warrior(body, body_sha_256)
        return warrior

    def _ensure_moderated(self, warrior):
        if warrior.moderation_passed is None:
            try:
                response = moderate([warrior.body])
            except TRANSIENT_MODERATION_ERRORS as error:
                raise CommandError('Moderation is unavailable right now; try again.') from error
            (result,) = response.results
            record_warrior_moderation(warrior, response, result.flagged, timezone.now())
            warrior.refresh_from_db()
        if warrior.moderation_passed is not True:
            raise CommandError('Moderation flagged this prompt; the hill will not show it.')

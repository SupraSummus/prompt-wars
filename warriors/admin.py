from django.contrib import admin
from django.utils import timezone

from .battles import Battle
from .rating_models import WarriorRating
from .text_unit import TextUnit
from .warriors import Warrior


class ReadOnlyModelAdminMixin:
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Warrior)
class WarriorAdmin(ReadOnlyModelAdminMixin, admin.ModelAdmin):
    list_display = (
        'id',
        'name',
        'created_at',
        'moderation_passed',
    )
    list_filter = (
        'moderation_passed',
    )
    search_fields = ('id', 'name', 'author_name')
    date_hierarchy = 'created_at'
    actions = ('take_down',)

    @admin.action(description='Take down: flag as failing moderation')
    def take_down(self, request, queryset):
        """The owner's veto, as a moderation verdict: off the ladder (`battleworthy`) and off the hill."""
        queryset.update(
            moderation_passed=False,
            moderation_model='owner',
            moderation_date=timezone.now(),
        )


@admin.register(WarriorRating)
class WarriorRatingAdmin(ReadOnlyModelAdminMixin, admin.ModelAdmin):
    list_display = (
        'warrior',
        'ranking',
        'rating',
        'games_played',
    )
    list_filter = (
        'ranking',
        'warrior__moderation_passed',
    )
    search_fields = ('id', 'warrior__id', 'warrior__name', 'warrior__author_name')
    date_hierarchy = 'rating_updated_at'


@admin.register(Battle)
class BattleAdmin(ReadOnlyModelAdminMixin, admin.ModelAdmin):
    list_display = ('warrior_1', 'warrior_2', 'scheduled_at', 'rated')
    list_filter = ('rated',)
    date_hierarchy = 'scheduled_at'

    def view_on_site(self, obj):
        # the battle page doesn't show an unrated battle, so no link to a 404
        return obj.get_absolute_url() if obj.rated else None


@admin.register(TextUnit)
class TextUnitAdmin(ReadOnlyModelAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'sha_256_hex', 'created_at')
    date_hierarchy = 'created_at'

    def sha_256_hex(self, obj):
        return obj.sha_256.hex()

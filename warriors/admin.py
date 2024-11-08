from django.contrib import admin

from .models import Arena, Battle, WarriorArena
from .text_unit import TextUnit
from .warriors import Warrior


class ReadOnlyModelAdminMixin:
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Arena)
class ArenaAdmin(admin.ModelAdmin):
    list_display = (
        'name', 'listed',
        'site',
    )
    search_fields = ('id', 'name')


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


@admin.register(WarriorArena)
class WarriorArenaAdmin(ReadOnlyModelAdminMixin, admin.ModelAdmin):
    list_display = (
        'id',
        'rating',
        'games_played',
    )
    list_filter = (
        'warrior__moderation_passed',
    )
    search_fields = ('id', 'warrior__name', 'warrior__author_name')
    date_hierarchy = 'warrior__created_at'

    fieldsets = (
        (None, {
            'fields': (
                'name',
                'author_name',
                'body',
                'created_at',
            ),
        }),
        ('Stats', {
            'fields': (
                'rating',
                'games_played',
            ),
        }),
        ('Moderation', {
            'fields': (
                'moderation_passed',
                'moderation_date',
                'moderation_model',
            ),
        }),
    )


@admin.register(Battle)
class BattleAdmin(ReadOnlyModelAdminMixin, admin.ModelAdmin):
    list_display = ('warrior_1', 'warrior_2', 'scheduled_at')
    date_hierarchy = 'scheduled_at'


@admin.register(TextUnit)
class TextUnitAdmin(ReadOnlyModelAdminMixin, admin.ModelAdmin):
    list_display = ('id', 'sha_256_hex', 'created_at')
    date_hierarchy = 'created_at'

    def sha_256_hex(self, obj):
        return obj.sha_256.hex()

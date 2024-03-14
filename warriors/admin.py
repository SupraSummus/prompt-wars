from django.contrib import admin
from django.utils.html import format_html

from .models import Arena, Battle, Warrior


class ReadOnlyModelAdminMixin:
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Arena)
class ArenaAdmin(admin.ModelAdmin):
    list_display = ('id', 'site', 'name')
    search_fields = ('id', 'name')


@admin.register(Warrior)
class WarriorAdmin(ReadOnlyModelAdminMixin, admin.ModelAdmin):
    list_display = (
        'id',
        'moderation_passed',
        'rating',
        'games_played',
        'created_at',
    )
    list_filter = (
        'moderation_passed',
    )
    search_fields = ('id', 'name', 'author_name')
    date_hierarchy = 'created_at'

    fieldsets = (
        (None, {
            'fields': (
                'name',
                'author_name',
                'body',
                'created_at',
                'secret_link',
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

    def secret_link(self, obj):
        return format_html(
            '<a href="{}">{}</a>',
            obj.get_absolute_url_secret(),
            obj.get_absolute_url_secret(),
        )


@admin.register(Battle)
class BattleAdmin(ReadOnlyModelAdminMixin, admin.ModelAdmin):
    list_display = ('warrior_1', 'warrior_2', 'scheduled_at')
    date_hierarchy = 'scheduled_at'

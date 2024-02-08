from django.contrib import admin

from .models import Battle, Warrior


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
        'moderation_passed',
        'rating',
        'games_played',
        'created_at',
    )
    list_filter = (
        'moderation_passed',
    )
    search_fields = ('id', 'name', 'author')
    date_hierarchy = 'created_at'


@admin.register(Battle)
class BattleAdmin(ReadOnlyModelAdminMixin, admin.ModelAdmin):
    list_display = ('warrior_1', 'warrior_2', 'scheduled_at')
    date_hierarchy = 'scheduled_at'

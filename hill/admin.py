from django.contrib import admin

from warriors.admin import ReadOnlyModelAdminMixin

from .models import Hill, HillAttempt, HouseBoss, Round


class HouseBossInline(admin.TabularInline):
    model = HouseBoss
    raw_id_fields = ('warrior',)
    extra = 0


@admin.register(Hill)
class HillAdmin(admin.ModelAdmin):
    list_display = ('__str__', 'enabled', 'llm', 'daily_attempt_limit', 'max_pending')
    inlines = (HouseBossInline,)

    def has_add_permission(self, request):
        # a singleton: `Hill.current()` reads one row
        return not Hill.objects.exists() and super().has_add_permission(request)

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Round)
class RoundAdmin(ReadOnlyModelAdminMixin, admin.ModelAdmin):
    list_display = (
        'number', 'starts_at', 'ends_at', 'boss', 'boss_name',
        'reign_round', 'boss_reason', 'closed_at',
    )
    list_select_related = ('boss',)


@admin.register(HillAttempt)
class HillAttemptAdmin(ReadOnlyModelAdminMixin, admin.ModelAdmin):
    """Attacks, read-only; a text is taken down from its Warrior (`WarriorAdmin.take_down`)."""
    list_display = (
        'id', 'hill_round', 'identity', 'state', 'late',
        'score', 'survived_chars', 'crown_block',
        'output_moderation_passed',
    )
    list_filter = (
        'state',
        'hill_round',
    )
    list_select_related = ('hill_round',)
    search_fields = ('id', 'identity')
    date_hierarchy = 'created_at'
    fields = (
        'hill_round', 'created_at', 'identity',
        'warrior', 'spell', 'display_name', 'display_author',
        'state', 'late', 'battle',
        'score', 'survived_chars', 'crown_block', 'output_moderation_passed',
    )

    @admin.display(description='Spell')
    def spell(self, obj):
        return obj.warrior.body

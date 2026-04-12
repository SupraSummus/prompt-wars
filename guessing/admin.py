from django.contrib import admin

from .models import Guess, GuessingTarget


@admin.register(GuessingTarget)
class GuessingTargetAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    readonly_fields = ('embedding', 'created_at')


@admin.register(Guess)
class GuessAdmin(admin.ModelAdmin):
    list_display = ('target', 'query', 'user', 'created_at')
    list_filter = ('target',)
    raw_id_fields = ('target', 'query', 'user')

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import GoogleAccount, User


class GoogleAccountInline(admin.TabularInline):
    model = GoogleAccount
    extra = 0
    readonly_fields = ('sub', 'created_at')


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    inlines = (GoogleAccountInline,)

from django.contrib import admin

from .models import Chunk


@admin.register(Chunk)
class ChunkAdmin(admin.ModelAdmin):
    pass

from django.contrib import admin
from .models import Event, Location

# Register your models here.

@admin.register(Event)
class EventAdmin(admin.ModelAdmin):
    list_display = ('name', 'start_date', 'end_date')
    search_fields = ('name',)
    ordering = ('-start_date',)

@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ('name', 'event', 'description')
    list_filter = ('event',)
    search_fields = ('name',)

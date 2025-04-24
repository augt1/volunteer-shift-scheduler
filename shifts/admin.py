from django.contrib import admin
from .models import Position, Shift, ShiftVolunteer

# Register your models here.

@admin.register(Position)
class PositionAdmin(admin.ModelAdmin):
    list_display = ('name', 'color')
    search_fields = ('name',)

@admin.register(Shift)
class ShiftAdmin(admin.ModelAdmin):
    list_display = ('position', 'date', 'start_time', 'end_time', 'location', 'max_volunteers')
    list_filter = ('position', 'date', 'location')
    search_fields = ('position__name', 'location__name')

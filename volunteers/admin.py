from django.contrib import admin
from .models import Volunteer

# Register your models here.

@admin.register(Volunteer)
class VolunteerAdmin(admin.ModelAdmin):
    list_display = ('first_name', 'last_name', 'email', 'phone_number', 'is_active')
    list_filter = ('is_active',)
    search_fields = ('first_name', 'last_name', 'email', 'phone_number')
    ordering = ('last_name', 'first_name')

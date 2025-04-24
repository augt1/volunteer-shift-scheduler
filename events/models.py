from django.db import models
from django.core.exceptions import ValidationError
from django.utils import timezone
from datetime import datetime, timedelta

# Create your models here.

class Event(models.Model):
    name = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    start_date = models.DateField()
    end_date = models.DateField()
    
    def clean(self):
        if self.end_date < self.start_date:
            raise ValidationError('End date must be after start date')
    
    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)
    
    def __str__(self):
        return f"{self.name} ({self.start_date} - {self.end_date})"

    def get_dates(self):
        """Returns a list of dates between start_date and end_date (inclusive)"""
        dates = []
        current_date = self.start_date
        while current_date <= self.end_date:
            dates.append(current_date)
            current_date += timedelta(days=1)
        return dates

class Location(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    address = models.CharField(max_length=255, blank=True)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='locations')
    
    def __str__(self):
        return f"{self.name}"

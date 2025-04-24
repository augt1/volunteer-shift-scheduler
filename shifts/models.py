from django.db import models
from django.contrib.auth.models import User
from volunteers.models import Volunteer
from events.models import Event, Location
from datetime import datetime, time, timedelta

class Position(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='positions')
    color = models.CharField(
        max_length=20,
        default='blue',
        choices=[
            ('slate', 'Slate'),
            ('gray', 'Gray'),
            ('red', 'Red'),
            ('orange', 'Orange'),
            ('amber', 'Amber'),
            ('yellow', 'Yellow'),
            ('lime', 'Lime'),
            ('green', 'Green'),
            ('emerald', 'Emerald'),
            ('teal', 'Teal'),
            ('cyan', 'Cyan'),
            ('sky', 'Sky'),
            ('blue', 'Blue'),
            ('indigo', 'Indigo'),
            ('violet', 'Violet'),
            ('purple', 'Purple'),
            ('fuchsia', 'Fuchsia'),
            ('pink', 'Pink'),
            ('rose', 'Rose'),
        ],
        help_text="Color theme for the position badge"
    )
    volunteers = models.ManyToManyField(
        Volunteer,
        through='PositionVolunteer',
        related_name='available_positions'
    )

    def __str__(self):
        return self.name

class PositionVolunteer(models.Model):
    position = models.ForeignKey(Position, on_delete=models.CASCADE)
    volunteer = models.ForeignKey(Volunteer, on_delete=models.CASCADE)
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = [('position', 'volunteer')]

    def __str__(self):
        return f"{self.volunteer} - {self.position}"

class Shift(models.Model):
    event = models.ForeignKey(Event, on_delete=models.CASCADE, related_name='shifts')
    location = models.ForeignKey(Location, on_delete=models.CASCADE, related_name='shifts')
    date = models.DateField()
    start_time = models.TimeField()
    end_time = models.TimeField()
    position = models.ForeignKey(Position, on_delete=models.PROTECT, null=True)
    max_volunteers = models.IntegerField(default=1, help_text="Maximum number of volunteers for this position")
    notes = models.TextField(blank=True)
    volunteers = models.ManyToManyField(
        Volunteer,
        through='ShiftVolunteer',
        related_name='shifts'
    )

    class Meta:
        ordering = ['date', 'start_time']

    def clean(self):
        from django.core.exceptions import ValidationError
        if not self.event or not self.date:
            return

        # For shifts starting before midnight
        # if self.start_time < time(0, 0):
        if self.date < self.event.start_date or self.date > self.event.end_date:
            raise ValidationError('Shift date must be within event dates before midnight')
        # For shifts starting after midnight
        # else:
        #     prev_day = self.date - timedelta(days=1)
        #     if prev_day < self.event.start_date or prev_day > self.event.end_date:
        #         raise ValidationError('Shift date must be within event dates')
        if self.location.event != self.event:
            raise ValidationError('Location must belong to the same event')

        # Check for duplicate shifts (same position, location, date, and time)
        duplicate_shifts = Shift.objects.filter(
            event=self.event,
            location=self.location,
            position=self.position,
            date=self.date,
            start_time=self.start_time
        )
        if self.pk:  # If updating existing shift
            duplicate_shifts = duplicate_shifts.exclude(pk=self.pk)
        if duplicate_shifts.exists():
            raise ValidationError('A shift for this position already exists at this location and time')

    def save(self, *args, **kwargs):
        self.clean()
        super().save(*args, **kwargs)

    def __str__(self):
        return f"{self.date} {self.start_time}-{self.end_time} ({self.position} at {self.location})"
    
    def get_absolute_url(self):
        from django.urls import reverse
        return reverse('day_view', args=[str(self.date)])
    
    def get_duration_hours(self):
        start_datetime = datetime.combine(self.date, self.start_time)
        end_datetime = datetime.combine(self.date, self.end_time)
        if end_datetime < start_datetime:  # If shift ends next day
            end_datetime += timedelta(days=1)
        duration = end_datetime - start_datetime
        return duration.total_seconds() / 3600  # Convert to hours

class ShiftVolunteer(models.Model):
    shift = models.ForeignKey(Shift, on_delete=models.CASCADE, null=True)
    volunteer = models.ForeignKey(Volunteer, on_delete=models.CASCADE)
    assigned_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    assigned_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    notes = models.TextField(blank=True)

    class Meta:
        unique_together = ['shift', 'volunteer']
        ordering = ['assigned_at']

    def __str__(self):
        return f"{self.shift} - {self.volunteer}"

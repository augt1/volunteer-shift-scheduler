from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import datetime, time, timedelta
from shifts.models import Position, Shift
from events.models import Event, Location

class Command(BaseCommand):
    help = 'Generate shifts for an event'

    def handle(self, *args, **options):
        # Get the current or next event
        today = timezone.now().date()
        current_event = Event.objects.filter(
            start_date__lte=today,
            end_date__gte=today
        ).first()
        
        if not current_event:
            current_event = Event.objects.filter(
                start_date__gte=today
            ).order_by('start_date').first()
        
        if not current_event:
            self.stdout.write(self.style.ERROR('No events found'))
            return

        # Get all locations and positions
        locations = Location.objects.filter(event=current_event)
        positions = Position.objects.all()

        # Define shift times (3-hour blocks from 9 AM to 5 AM next day)
        shift_times = [
            (time(9, 0), time(12, 0), 3),   # Morning shift
            (time(12, 0), time(15, 0), 3),  # Early afternoon shift
            (time(15, 0), time(18, 0), 3),  # Late afternoon shift
            (time(18, 0), time(21, 0), 3),  # Evening shift
            (time(21, 0), time(0, 0), 3),   # Night shift
            (time(0, 0), time(2, 0), 2),    # Late night shift
            (time(2, 0), time(5, 0), 2),    # Early morning shift
        ]

        # Generate shifts for each day of the event
        event_length = (current_event.end_date - current_event.start_date).days + 1
        
        for day_offset in range(event_length):
            current_date = current_event.start_date + timedelta(days=day_offset)
            
            for location in locations:
                for start_time, end_time, max_volunteers in shift_times:
                    # Determine the correct date for the shift
                    shift_date = current_date
                    if start_time < time(9, 0):  # If it's an early morning shift
                        shift_date = current_date + timedelta(days=1)
                    
                    # Create shifts for each position
                    for position in positions:
                        try:
                            Shift.objects.create(
                                event=current_event,
                                location=location,
                                date=shift_date,
                                start_time=start_time,
                                end_time=end_time,
                                position=position,
                                max_volunteers=max_volunteers
                            )
                            self.stdout.write(
                                self.style.SUCCESS(
                                    f'Created shifts for {location.name} on {shift_date} at {start_time.strftime("%H:%M:%S")}'
                                )
                            )
                        except Exception as e:
                            self.stdout.write(
                                self.style.WARNING(
                                    f'Failed to create shift for {location.name} on {shift_date} at {start_time.strftime("%H:%M:%S")}: {str(e)}'
                                )
                            )

        self.stdout.write(
            self.style.SUCCESS(
                f'Successfully generated shifts from {current_event.start_date} to {current_event.end_date}'
            )
        )

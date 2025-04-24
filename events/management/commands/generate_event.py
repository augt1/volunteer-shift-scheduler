from datetime import datetime, timedelta
from django.core.management.base import BaseCommand
from django.utils import timezone
from events.models import Event, Location
from shifts.models import Position

class Command(BaseCommand):
    help = 'Generate the event for 30 April - 5 May'

    def handle(self, *args, **options):
        # Create event with specific dates
        start_date = datetime(2025, 4, 30).date()
        end_date = datetime(2025, 5, 5).date()
        
        event = Event.objects.create(
            name='Comicdom Con Athens 2025',
            description='The biggest comics convention in Greece',
            start_date=start_date,
            end_date=end_date
        )
        
        # Create locations with addresses
        locations = [
            {
                'name': 'Serafeio',
                'description': 'Main convention area',
                'address': 'Pireos & Petrou Ralli, Athens 118 54'
            },
            {
                'name': 'Gym',
                'description': 'Gaming and activities area',
                'address': 'Pireos & Petrou Ralli, Athens 118 54'
            },
            {
                'name': 'Panas',
                'description': 'Workshops and panels',
                'address': 'Pireos & Petrou Ralli, Athens 118 54'
            },
            {
                'name': 'RHDS',
                'description': 'Artist alley and exhibitions',
                'address': 'Pireos & Petrou Ralli, Athens 118 54'
            }
        ]
        
        # Create location objects
        for loc_data in locations:
            Location.objects.create(
                event=event,
                name=loc_data['name'],
                description=loc_data['description'],
                address=loc_data['address']
            )
        
        # Create positions
        positions = [
            Position.objects.create(
                name='Pass Check',
                description='Check participant passes and manage entry points',
                event=event,
                color='blue'
            ),
            Position.objects.create(
                name='Registration',
                description='Handle participant registration and check-in',
                event=event,
                color='green'
            ),
            Position.objects.create(
                name='Floor',
                description='Manage floor operations and participant flow',
                event=event,
                color='purple'
            ),
            Position.objects.create(
                name='Decoration',
                description='Handle venue decoration and aesthetics',
                event=event,
                color='pink'
            ),
            Position.objects.create(
                name='Social',
                description='Manage social media and participant engagement',
                event=event,
                color='cyan'
            ),
        ]
        
        self.stdout.write(
            self.style.SUCCESS(f'Successfully created event "{event.name}" with {len(locations)} locations and {len(positions)} positions')
        )

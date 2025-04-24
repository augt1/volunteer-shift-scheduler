from django.core.management.base import BaseCommand
from shifts.models import Position

INITIAL_POSITIONS = [
    {
        'name': 'Floor',
        'description': 'Monitor the event floor, assist attendees, and maintain order',
        'max_volunteers': 4
    },
    {
        'name': 'Registration',
        'description': 'Check in attendees, hand out badges and materials',
        'max_volunteers': 3
    },
    {
        'name': 'Pass Check',
        'description': 'Verify attendee passes and manage access control',
        'max_volunteers': 2
    },
    {
        'name': 'Decoration',
        'description': 'Set up and maintain event decorations and signage',
        'max_volunteers': 3
    }
]

class Command(BaseCommand):
    help = 'Generate initial positions for the volunteer system'

    def handle(self, *args, **options):
        self.stdout.write('Creating initial positions...')
        
        positions_created = 0
        for position_data in INITIAL_POSITIONS:
            position, created = Position.objects.get_or_create(
                name=position_data['name'],
                defaults={
                    'description': position_data['description'],
                    'max_volunteers': position_data['max_volunteers']
                }
            )
            
            if created:
                positions_created += 1
                self.stdout.write(self.style.SUCCESS(
                    f'Created position: {position.name}'
                ))
            else:
                self.stdout.write(self.style.WARNING(
                    f'Position already exists: {position.name}'
                ))
        
        self.stdout.write(self.style.SUCCESS(
            f'Successfully created {positions_created} positions'
        ))

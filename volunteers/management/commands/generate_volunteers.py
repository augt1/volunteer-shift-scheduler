from django.core.management.base import BaseCommand
from faker import Faker
from volunteers.models import Volunteer
import random

class Command(BaseCommand):
    help = 'Generates fake volunteers for testing'

    def add_arguments(self, parser):
        parser.add_argument('count', type=int, help='Number of volunteers to generate')

    def handle(self, *args, **kwargs):
        fake = Faker()
        count = kwargs['count']

        self.stdout.write(f'Generating {count} volunteers...')

        for _ in range(count):
            first_name = fake.first_name()
            last_name = fake.last_name()
            email = f"{first_name.lower()}.{last_name.lower()}@{fake.domain_name()}"
            
            # Generate a valid phone number in the format +1XXXXXXXXXX
            phone_number = f"+1{fake.numerify('##########')}"
            
            volunteer = Volunteer.objects.create(
                first_name=first_name,
                last_name=last_name,
                email=email,
                phone_number=phone_number,
                notes=fake.paragraph(nb_sentences=2),
                is_active=random.choice([True, True, True, False])  # 75% chance of being active
            )

        self.stdout.write(self.style.SUCCESS(f'Successfully generated {count} volunteers'))

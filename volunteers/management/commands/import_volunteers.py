import pandas as pd
from django.core.management.base import BaseCommand
from volunteers.models import Volunteer
from shifts.models import Position, PositionVolunteer
from django.contrib.auth.models import User

class Command(BaseCommand):
    help = 'Import volunteers from a CSV or Excel file'

    def add_arguments(self, parser):
        parser.add_argument('file_path', type=str, help='Path to the CSV or Excel file')

    def format_phone(self, phone):
        if pd.isna(phone):
            return ''
        
        phone = str(phone).strip()
        if not phone:
            return ''
        
        # Remove any spaces or special characters
        phone = ''.join(filter(lambda x: x.isdigit() or x in ['+'], phone))
        
        # Handle different formats
        if phone.startswith('00'):
            return '+' + phone[2:]
        elif not phone.startswith('+'):
            return '+30' + phone
        return phone

    def handle(self, *args, **options):
        file_path = options['file_path']
        
        try:
            # Read file based on extension
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path)
            else:
                df = pd.read_excel(file_path)

            required_columns = ['Name', 'Surname', 'Email', 'Mobile phone number', 'processed in application', 'position']
            
            # Verify required columns exist
            missing_columns = [col for col in required_columns if col not in df.columns]
            if missing_columns:
                self.stdout.write(self.style.ERROR(
                    f'Missing required columns: {", ".join(missing_columns)}'
                ))
                return

            # Get all positions for matching
            positions = {p.name.lower(): p for p in Position.objects.all()}
            
            # Get or create system user for position assignments
            system_user, _ = User.objects.get_or_create(
                username='system',
                defaults={'is_staff': True, 'is_superuser': True}
            )

            # Import volunteers
            created_count = 0
            updated_count = 0
            position_assigned_count = 0

            for _, row in df.iterrows():
                # Skip if not processed in application
                if pd.notna(row['processed in application']) and row['processed in application'].lower() != 'yes':
                    continue

                # Format phone number
                phone = self.format_phone(row['Mobile phone number'])

                # Create or update volunteer
                email = row['Email']
                if pd.isna(email):
                    self.stdout.write(self.style.WARNING(f'Skipping row with empty email'))
                    continue

                volunteer, created = Volunteer.objects.update_or_create(
                    email=str(email).strip(),
                    defaults={
                        'first_name': str(row['Name']).strip() if pd.notna(row['Name']) else '',
                        'last_name': str(row['Surname']).strip() if pd.notna(row['Surname']) else '',
                        'phone_number': phone,
                    }
                )

                if created:
                    created_count += 1
                else:
                    updated_count += 1

                # Assign position if it matches
                if pd.notna(row['position']):
                    position_name = row['position'].strip().lower()
                    if position_name in positions:
                        position = positions[position_name]
                        # Create position assignment if it doesn't exist
                        _, created = PositionVolunteer.objects.get_or_create(
                            volunteer=volunteer,
                            position=position,
                            defaults={'assigned_by': system_user}
                        )
                        if created:
                            position_assigned_count += 1

            self.stdout.write(self.style.SUCCESS(
                f'Successfully imported {created_count} new volunteers and updated {updated_count} existing volunteers.\n'
                f'Assigned {position_assigned_count} position assignments.'
            ))

        except Exception as e:
            self.stdout.write(self.style.ERROR(f'Error importing volunteers: {str(e)}'))
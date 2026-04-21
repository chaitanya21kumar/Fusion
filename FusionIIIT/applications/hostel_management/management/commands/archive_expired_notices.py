from django.core.management.base import BaseCommand
from applications.hostel_management.services import archive_expired_notices

class Command(BaseCommand):
    help = 'Automatically archives notices that have passed their end date.'

    def handle(self, *args, **options):
        self.stdout.write('Starting notice archival process...')
        count = archive_expired_notices()
        self.stdout.write(self.style.SUCCESS(f'Successfully archived {count} expired notices.'))

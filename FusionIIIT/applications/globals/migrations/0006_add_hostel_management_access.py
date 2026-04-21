# Generated migration for hostel management module access

from django.db import migrations


def add_hostel_management_access(apps, schema_editor):
    """Add hostel_management access for student designation."""
    ModuleAccess = apps.get_model('globals', 'ModuleAccess')
    
    # Update existing student entry or create new one
    student_access, created = ModuleAccess.objects.get_or_create(
        designation='student',
        defaults={
            'hostel_management': True,
            'course_registration': True,
            'program_and_curriculum': True,
        }
    )
    if not created:
        student_access.hostel_management = True
        student_access.save()
    
    # Add access for Hall Caretaker designation (if exists)
    caretaker_access, created = ModuleAccess.objects.get_or_create(
        designation='hall_caretaker',
        defaults={
            'hostel_management': True,
        }
    )
    if not created:
        caretaker_access.hostel_management = True
        caretaker_access.save()
    
    # Add access for Hall Warden designation (if exists)
    warden_access, created = ModuleAccess.objects.get_or_create(
        designation='hall_warden',
        defaults={
            'hostel_management': True,
        }
    )
    if not created:
        warden_access.hostel_management = True
        warden_access.save()


def remove_hostel_management_access(apps, schema_editor):
    """Remove hostel_management access (reverse migration)."""
    ModuleAccess = apps.get_model('globals', 'ModuleAccess')
    
    # Just set hostel_management to False for these designations
    ModuleAccess.objects.filter(
        designation__in=['student', 'hall_caretaker', 'hall_warden']
    ).update(hostel_management=False)


class Migration(migrations.Migration):

    dependencies = [
        ('globals', '0005_moduleaccess_database'),
    ]

    operations = [
        migrations.RunPython(
            add_hostel_management_access,
            remove_hostel_management_access
        ),
    ]

from django.db import migrations

class Migration(migrations.Migration):

    dependencies = [
        ('hostel_management', '0007_auto_20260419_0105'),
    ]

    operations = [
        migrations.RunSQL(
            sql=[
                'ALTER TABLE "hostel_management_room" ALTER COLUMN "hostel_id" TYPE varchar(20) USING "hostel_id"::varchar(20);',
                'ALTER TABLE "hostel_management_roomallotment" ALTER COLUMN "hostel_id" TYPE varchar(20) USING "hostel_id"::varchar(20);',
                'ALTER TABLE "hostel_management_hostelstaffassignment" ALTER COLUMN "hostel_id" TYPE varchar(20) USING "hostel_id"::varchar(20);',
                'ALTER TABLE "hostel_management_hostelauditlog" ALTER COLUMN "hostel_id" TYPE varchar(20) USING "hostel_id"::varchar(20);',
            ],
            reverse_sql=[
                'ALTER TABLE "hostel_management_room" ALTER COLUMN "hostel_id" TYPE integer USING "hostel_id"::integer;',
                'ALTER TABLE "hostel_management_roomallotment" ALTER COLUMN "hostel_id" TYPE integer USING "hostel_id"::integer;',
                'ALTER TABLE "hostel_management_hostelstaffassignment" ALTER COLUMN "hostel_id" TYPE integer USING "hostel_id"::integer;',
                'ALTER TABLE "hostel_management_hostelauditlog" ALTER COLUMN "hostel_id" TYPE integer USING "hostel_id"::integer;',
            ]
        ),
    ]

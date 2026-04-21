import datetime
from django.db import models
from django.db.models import Q, UniqueConstraint
from django.contrib.auth.models import User
from applications.globals.models import ExtraInfo, Staff, Faculty
from applications.academic_information.models import Student
from django.utils import timezone


# ══════════════════════════════════════════════════════════════
# ENUMS & CONSTANTS (TextChoices & IntegerChoices)
# ══════════════════════════════════════════════════════════
class LeaveStatusChoices(models.TextChoices):
    """Leave application status options."""
    PENDING = "Pending", "Pending"
    APPROVED = "Approved", "Approved"
    REJECTED = "Rejected", "Rejected"
    CANCELLED = "Cancelled", "Cancelled"


class AttendanceStatus(models.TextChoices):
    """Student attendance status options."""
    PRESENT = "Present", "Present"
    ABSENT = "Absent", "Absent"
    ON_LEAVE = "OnLeave", "OnLeave"
    NOT_MARKED = "NotMarked", "NotMarked"


class ComplaintStatusChoices(models.TextChoices):
    """Complaint status options."""
    SUBMITTED = "Submitted", "Submitted"
    IN_PROGRESS = "InProgress", "In Progress"
    ESCALATED = "Escalated", "Escalated"
    RESOLVED = "Resolved", "Resolved"
    CLOSED = "Closed", "Closed"


class ComplaintCategoryChoices(models.TextChoices):
    """Complaint category for routing."""
    MAINTENANCE = "Maintenance", "Maintenance"
    CLEANING = "Cleaning", "Cleaning"
    SECURITY = "Security", "Security"
    OTHER = "Other", "Other"


class ComplaintPriorityChoices(models.TextChoices):
    """Complaint priority levels."""
    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"
    CRITICAL = "critical", "Critical"


class FineStatusChoices(models.TextChoices):
    """Fine payment status."""
    PENDING = "pending", "Pending"
    PAID = "paid", "Paid"
    WAIVED = "waived", "Waived"
    CANCELLED = "cancelled", "Cancelled"


class FineCategoryChoices(models.TextChoices):
    """Hostel fine violation categories."""
    RULE_VIOLATION = "HostelRuleViolation", "Hostel Rule Violation"
    PROPERTY_DAMAGE = "PropertyDamage", "Property Damage"
    ATTENDANCE_VIOLATION = "AttendanceViolation", "Attendance Violation"
    ROOM_STANDARDS = "RoomStandardsViolation", "Room Standards Violation"


class InventoryCategory(models.TextChoices):
    MAINTENANCE = "Maintenance", "Maintenance"
    CLEANING = "Cleaning", "Cleaning"
    BEDDING = "Bedding", "Bedding"
    EQUIPMENT = "Equipment", "Equipment"
    FURNITURE = "Furniture", "Furniture"
    ELECTRONICS = "Electronics", "Electronics"
    OTHER = "Other", "Other"


class InventoryCondition(models.TextChoices):
    GOOD = "Good", "Good"
    DAMAGED = "Damaged", "Damaged"
    MISSING = "Missing", "Missing"


class DiscrepancyType(models.TextChoices):
    MISSING = "Missing", "Missing"
    DAMAGED = "Damaged", "Damaged"
    DEPLETED = "Depleted", "Depleted"


class ResourceRequestType(models.TextChoices):
    NEW = "New", "New"
    REPLACEMENT = "Replacement", "Replacement"
    ADDITIONAL = "Additional", "Additional"


class ResourceRequestStatus(models.TextChoices):
    PENDING = "Pending", "Pending"
    APPROVED = "Approved", "Approved"
    REJECTED = "Rejected", "Rejected"


class NoticePriority(models.TextChoices):
    NORMAL = "Normal", "Normal"
    IMPORTANT = "Important", "Important"
    URGENT = "Urgent", "Urgent"


class NoticeStatus(models.TextChoices):
    DRAFT = "Draft", "Draft"
    PUBLISHED = "Published", "Published"
    ARCHIVED = "Archived", "Archived"


class RoomChangeStatusChoices(models.TextChoices):
    """Room change request status."""
    PENDING = "pending", "Pending"
    APPROVED_WARDEN = "approved_warden", "Approved by Warden"
    APPROVED_CARETAKER = "approved_caretaker", "Approved by Caretaker"
    REJECTED = "rejected", "Rejected"
    COMPLETED = "completed", "Completed"


class RoomTypeChoices(models.TextChoices):
    """Room occupancy types."""
    SINGLE = "single", "Single Seater"
    DOUBLE = "double", "Double Seater"
    TRIPLE = "triple", "Triple Seater"


class BookingStatusChoices(models.TextChoices):
    """Guest room booking status."""
    PENDING = "Pending", "Pending"
    APPROVED = "Approved", "Approved"
    REJECTED = "Rejected", "Rejected"
    CHECKED_IN = "CheckedIn", "Checked In"
    COMPLETED = "Completed", "Completed"
    CANCELLED = "Cancelled", "Cancelled"


class DamageSeverityChoices(models.TextChoices):
    """Guest room damage severity levels."""
    NONE = "None", "None"
    MINOR = "Minor", "Minor"
    MODERATE = "Moderate", "Moderate"
    MAJOR = "Major", "Major"
    SEVERE = "Severe", "Severe"


class HostelManagementConstants:
    ROOM_STATUS = (
        ('Booked', 'Booked'),
        ('CheckedIn', 'Checked In'),
        ('Available', 'Available'),
        ('UnderMaintenance', 'Under Maintenance'),
        )

    DAYS_OF_WEEK = (
            ('Monday', 'Monday'),
            ('Tuesday', 'Tuesday'),
            ('Wednesday', 'Wednesday'),
            ('Thursday', 'Thursday'),
            ('Friday', 'Friday'),
            ('Saturday', 'Saturday'),
            ('Sunday', 'Sunday')
        )

    BOOKING_STATUS = (
    ("Confirmed" , 'Confirmed'),
    ("Pending" , 'Pending'),
    ("Rejected" , 'Rejected'),
    ("Canceled" , 'Canceled'),
    ("CancelRequested" , 'Cancel Requested'),
    ("CheckedIn" , 'Checked In'),
    ("Complete", 'Complete'),
    ("Forward", 'Forward')
    )    

# Alias for selectors that reference GuestRoomBookingStatusChoices
GuestRoomBookingStatusChoices = BookingStatusChoices


# ══════════════════════════════════════════════════════════════
# HOSTEL SETUP FOUNDATION — NEW MODELS
# ══════════════════════════════════════════════════════════════

class HostelTypeChoices(models.TextChoices):
    """Hostel gender type options."""
    BOYS = "Boys", "Boys"
    GIRLS = "Girls", "Girls"
    MIXED = "Mixed", "Mixed"


class HostelStatusChoices(models.TextChoices):
    """Hostel operational status options."""
    INACTIVE = "Inactive", "Inactive"
    ACTIVE = "Active", "Active"
    UNDER_MAINTENANCE = "UnderMaintenance", "Under Maintenance"


class RoomSetupStatusChoices(models.TextChoices):
    """Room status options for the new Hostel→Room system."""
    AVAILABLE = "Available", "Available"
    OCCUPIED = "Occupied", "Occupied"
    UNDER_MAINTENANCE = "UnderMaintenance", "Under Maintenance"


class StaffRoleChoices(models.TextChoices):
    """Hostel staff role options."""
    WARDEN = "Warden", "Warden"
    CARETAKER = "Caretaker", "Caretaker"


class Hostel(models.Model):
    """
    Central hostel configuration entity (foundation chunk).

    Replaces the legacy Hall model for new hostel setup workflows.
    """
    hall_id = models.CharField(max_length=20, primary_key=True)
    name = models.CharField(max_length=100, unique=True)
    type = models.CharField(
        max_length=10,
        choices=HostelTypeChoices.choices,
        default=HostelTypeChoices.BOYS
    )
    total_capacity = models.PositiveIntegerField()
    floor_count = models.PositiveIntegerField(default=1)
    room_config_json = models.JSONField(
        default=dict, blank=True,
        help_text='JSON config for auto-generating rooms. Schema: {"floors": [{"floor": 1, "rooms_per_floor": 20, "capacity_per_room": 2}]}'
    )
    status = models.CharField(
        max_length=20,
        choices=HostelStatusChoices.choices,
        default=HostelStatusChoices.INACTIVE
    )
    created_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='hostels_created'
    )
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hostel_management_hostel'
        ordering = ['name']

    def __str__(self):
        return f"{self.name} ({self.get_type_display()}) — {self.get_status_display()}"


class Room(models.Model):
    """
    Room record auto-created from Hostel.room_config_json via post_save signal.

    Tracks floor, capacity, and current occupancy for each room.
    """
    hostel = models.ForeignKey(
        Hostel, on_delete=models.CASCADE, related_name='rooms_setup', to_field='hall_id'
    )
    room_number = models.CharField(max_length=20)
    floor = models.PositiveIntegerField(default=1)
    capacity = models.PositiveIntegerField(default=1)
    current_occupancy = models.PositiveIntegerField(default=0)
    status = models.CharField(
        max_length=20,
        choices=RoomSetupStatusChoices.choices,
        default=RoomSetupStatusChoices.AVAILABLE
    )

    class Meta:
        db_table = 'hostel_management_room'
        ordering = ['hostel', 'floor', 'room_number']
        unique_together = ['hostel', 'room_number']

    def __str__(self):
        return f"{self.hostel.name} — Floor {self.floor}, Room {self.room_number}"


class HostelStaffAssignment(models.Model):
    """
    Unified staff assignment model for wardens and caretakers.

    - BR-HM-019.a: Hostel must have ≥1 active Warden and ≥1 active Caretaker before status → Active
    - BR-HM-019.b: Warn if staff has concurrent active assignments beyond system limit
    """
    hostel = models.ForeignKey(
        Hostel, on_delete=models.CASCADE, related_name='staff_assignments', to_field='hall_id'
    )
    user = models.ForeignKey(
        User, on_delete=models.CASCADE, related_name='hostel_staff_assignments'
    )
    role = models.CharField(
        max_length=10,
        choices=StaffRoleChoices.choices
    )
    start_date = models.DateField()
    end_date = models.DateField(null=True, blank=True)
    is_active = models.BooleanField(default=True)
    assigned_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='staff_assignments_made'
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hostel_management_hostelstaffassignment'
        ordering = ['-is_active', '-start_date']

    def __str__(self):
        return f"{self.user.get_full_name()} — {self.get_role_display()} at {self.hostel.name}"


class HostelAuditLog(models.Model):
    """
    Append-only audit log for hostel configuration and status changes.

    All status changes and staff assignment changes are logged here.
    """
    hostel = models.ForeignKey(
        Hostel, on_delete=models.CASCADE, related_name='audit_logs', to_field='hall_id'
    )
    action = models.CharField(max_length=100)
    performed_by = models.ForeignKey(
        User, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='hostel_audit_actions'
    )
    detail_json = models.JSONField(default=dict, blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hostel_management_hostelauditlog'
        ordering = ['-timestamp']

    def __str__(self):
        return f"[{self.timestamp}] {self.hostel.name}: {self.action}"


# ══════════════════════════════════════════════════════════════
# POST-SAVE SIGNAL: Auto-create Room records from room_config_json
# ══════════════════════════════════════════════════════════════

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=Hostel)
def auto_create_rooms_from_config(sender, instance, created, **kwargs):
    """
    Auto-create Room records when a Hostel is saved with room_config_json.

    Triggered on create only (to avoid duplicates on update).
    If rooms already exist for this hostel, skip creation.
    """
    if not created:
        return

    config = instance.room_config_json
    if not config or not isinstance(config, dict):
        return

    floors = config.get('floors', [])
    if not floors:
        return

    # Only create if no rooms exist yet
    if Room.objects.filter(hostel=instance).exists():
        return

    rooms_to_create = []
    for floor_config in floors:
        floor_num = floor_config.get('floor', 1)
        rooms_per_floor = floor_config.get('rooms_per_floor', 0)
        capacity = floor_config.get('capacity_per_room', 1)

        for room_idx in range(1, rooms_per_floor + 1):
            room_number = f"{floor_num}{str(room_idx).zfill(2)}"
            rooms_to_create.append(Room(
                hostel=instance,
                room_number=room_number,
                floor=floor_num,
                capacity=capacity,
                current_occupancy=0,
                status=RoomSetupStatusChoices.AVAILABLE
            ))

    if rooms_to_create:
        Room.objects.bulk_create(rooms_to_create)







class HallStatusChoices(models.TextChoices):
    """Hostel Hall status options."""
    ACTIVE = "active", "Active"
    MAINTENANCE = "maintenance", "Under Maintenance"
    INACTIVE = "inactive", "Inactive"


class RoomVacationStatusChoices(models.TextChoices):
    PENDING = "pending", "Pending Clearance"
    VERIFIED = "verified", "Verified by Caretaker"
    APPROVED = "approved", "Approved by Warden"
    COMPLETED = "completed", "Vacation Completed"


class ExtendedStayStatusChoices(models.TextChoices):
    SUBMITTED = "submitted", "Submitted"
    UNDER_REVIEW = "under_review", "Under Review"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class Hall(models.Model):
    """
    LEGACY MODEL - DEPRECATED
    Use 'Hostel' model instead for the new architecture.
    """
    """
    Records information related to various Hall of Residences.

    'hall_id' and 'hall_name' store id and name of a Hall of Residence. 
    'max_accomodation' stores maximum accomodation limit of a Hall of Residence.
    'number_students' stores number of students currently residing in a Hall of Residence.
    """
    hall_id = models.CharField(max_length=10)
    hall_name = models.CharField(max_length=50)
    max_accomodation = models.IntegerField(default=0)
    number_students = models.PositiveIntegerField(default=0)
    assigned_batch = models.CharField(max_length=50, null=True, blank=True)
    TYPE_OF_SEATER_CHOICES = [
        ('single', 'Single Seater'),
        ('double', 'Double Seater'),
        ('triple', 'Triple Seater'),
    ]
    type_of_seater = models.CharField(max_length=50, choices=TYPE_OF_SEATER_CHOICES, default='single')
    status = models.CharField(max_length=20, choices=HallStatusChoices.choices, default=HallStatusChoices.ACTIVE)
    def __str__(self):
        return self.hall_id 


class HallCaretaker(models.Model):
    """
    LEGACY MODEL - DEPRECATED
    Use 'HostelStaffAssignment' model instead.
    """
    """
    Records Caretakers of Hall of Residences.

    'hall' refers to related Hall of Residence.
    'staff' refers to related Staff details.
    'assigned_date' stores when the caretaker was assigned.
    'is_active' indicates if the assignment is currently active.
    """
    hall = models.ForeignKey(Hall, on_delete=models.CASCADE)
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE)
    assigned_date = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return str(self.hall) + '  (' + str(self.staff.id.user.username) + ')'


class HallWarden(models.Model):
    """
    LEGACY MODEL - DEPRECATED
    Use 'HostelStaffAssignment' model instead.
    """
    """
    Records Wardens of Hall of Residences.

    'hall' refers to related Hall of Residence.
    'faculty' refers to related Faculty details.
    'assigned_date' stores when the warden was assigned.
    'is_active' indicates if the assignment is currently active.
    """
    hall = models.ForeignKey(Hall, on_delete=models.CASCADE)
    faculty = models.ForeignKey(Faculty, on_delete=models.CASCADE)
    assigned_date = models.DateTimeField(auto_now_add=True)
    is_active = models.BooleanField(default=True)

    def __str__(self):
        return str(self.hall) + '  (' + str(self.faculty.id.user.username) + ')'
    



class GuestRoomBooking(models.Model):
    """
    Refined GuestRoomBooking model (Chunk 12).
    Tracks the entire lifecycle of a guest room booking.
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='guest_room_bookings')
    room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='guest_bookings')
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='guest_room_bookings', to_field='hall_id')
    guest_name = models.CharField(max_length=255)
    guest_phone = models.CharField(max_length=20, null=True, blank=True)
    guest_email = models.EmailField(null=True, blank=True)
    guest_address = models.TextField(blank=True, default='')
    nationality = models.CharField(max_length=100, blank=True, default='')
    visit_purpose = models.TextField() # Min length enforced in serializer
    check_in_date = models.DateField()
    check_out_date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=BookingStatusChoices.choices,
        default=BookingStatusChoices.PENDING
    )
    per_night_rate = models.DecimalField(max_digits=10, decimal_places=2)
    total_charges = models.DecimalField(max_digits=10, decimal_places=2)
    advance_charge_breakdown_json = models.JSONField(default=dict, blank=True)
    
    # ID Verification Fields (Fill on Check-In)
    id_proof_type = models.CharField(max_length=50, null=True, blank=True)
    id_proof_number = models.CharField(max_length=50, null=True, blank=True)
    id_verified_at = models.DateTimeField(null=True, blank=True)
    
    caretaker_remarks = models.TextField(blank=True, null=True)
    
    booking_uid = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hostel_management_guestroombooking'
        ordering = ['-created_at']

    def __str__(self):
        return f"Booking {self.booking_uid} - {self.guest_name} ({self.status})"

    def save(self, *args, **kwargs):
        if not self.booking_uid:
            import uuid
            self.booking_uid = f"GRB-{uuid.uuid4().hex[:8].upper()}"
        super().save(*args, **kwargs)



class StaffSchedule(models.Model):
    """
    Records schedule of staffs in various Hall of Residences.

    'hall' refers to the related Hall of Residence.
    'staff' refers to the Staff member.
    'shift_type' stores the type of shift (e.g., 'Caretaker', 'Security').
    'day_of_week' stores the assigned day of a schedule from DAYS_OF_WEEK.
    'start_time' stores the start time of a schedule.
    'end_time' stores the end time of a schedule.
    """    
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='schedules')   
    staff = models.ForeignKey(Staff, on_delete=models.CASCADE, related_name='schedules')
    shift_type = models.CharField(max_length=100, default='Caretaker')
    day_of_week = models.CharField(max_length=15, choices=HostelManagementConstants.DAYS_OF_WEEK)
    start_time = models.TimeField(null=True, blank=True)
    end_time = models.TimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    def __str__(self):
        return str(self.staff) + ' - ' + str(self.day_of_week) + ' ' + str(self.start_time) + '->' + str(self.end_time)
    

class Notice(models.Model):
    """
    Refined Notice entity (HM-WF-110).
    Manages the lifecycle from draft to archival with priority and scoping.
    """
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='notices_new', null=True, blank=True)
    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='created_notices')
    title = models.CharField(max_length=200)
    description = models.TextField()
    priority = models.CharField(max_length=15, choices=NoticePriority.choices, default=NoticePriority.NORMAL)
    start_date = models.DateField(default=timezone.now)
    end_date = models.DateField()
    status = models.CharField(max_length=15, choices=NoticeStatus.choices, default=NoticeStatus.DRAFT)
    attachment = models.FileField(upload_to='hostel/notices/attachments/', null=True, blank=True)
    notice_uid = models.CharField(max_length=50, unique=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hostel_management_notice'
        ordering = ['-created_at']

    def __str__(self):
        return f"[{self.priority}] {self.title} ({self.status})"


class NoticeReadStatus(models.Model):
    """
    Tracks if a student has viewed a notice.
    """
    notice = models.ForeignKey(Notice, on_delete=models.CASCADE, related_name='read_statuses')
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='notices_read')
    read_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hostel_management_noticereadstatus'
        unique_together = ['notice', 'student']


class HostelNoticeBoard(models.Model):
    """
    LEGACY MODEL - DEPRECATED
    Records notices of various Hall of Residences.

    'hall' refers to the related Hall of Residence.
    'posted_by' refers to the user who posted it.
    'title' stores the title of the notice.
    'description' stores description of a notice.
    'content_file' stores any file uploaded as part of notice.
    'is_active' indicates if the notice is currently active.
    'posted_date' stores when the notice was posted.
    'archive_date' stores when the notice was archived.
    """    
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='notices')
    posted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='hostel_notices')
    title = models.CharField(max_length=200)
    description = models.TextField(blank=True)
    content_file = models.FileField(upload_to='hostel_management/notices/', blank=True, null=True)
    is_active = models.BooleanField(default=True)
    posted_date = models.DateTimeField(auto_now_add=True)
    archive_date = models.DateTimeField(null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-posted_date']

    def __str__(self):
        return self.title



class HallRoom(models.Model):
    """
    LEGACY MODEL - DEPRECATED
    Use 'Room' model instead for the new architecture.
    """
    """
    Records information related to rooms in various Hall of Residences

    'hall' refers to the related Hall of Residence.
    'room_number' stores the room number.
    'block_number' stores the block number a room belongs to.
    'capacity' stores the maximum occupancy limit of a room.
    'current_occupancy' stores the current number of occupants of a room.
    'room_type' stores the type of room (single/double/triple).
    'status' stores the current status of the room.
    """    
    ROOM_TYPE_CHOICES = [
        ('single', 'Single Seater'),
        ('double', 'Double Seater'),
        ('triple', 'Triple Seater'),
    ]
    
    ROOM_STATUS_CHOICES = [
        ('available', 'Available'),
        ('booked', 'Booked'),
        ('checked_in', 'Checked In'),
        ('maintenance', 'Under Maintenance'),
    ]
    
    hall = models.ForeignKey(Hall, on_delete=models.CASCADE, related_name='rooms')
    room_number = models.CharField(max_length=20)
    block_number = models.CharField(max_length=10)
    capacity = models.IntegerField(default=1)
    current_occupancy = models.IntegerField(default=0)
    room_type = models.CharField(max_length=20, choices=ROOM_TYPE_CHOICES, default='single')
    status = models.CharField(max_length=20, choices=ROOM_STATUS_CHOICES, default='available')
    created_at = models.DateTimeField(auto_now_add=True, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True, null=True, blank=True)

    class Meta:
        ordering = ['hall', 'block_number', 'room_number']

    def __str__(self):
        return f"{self.hall} - Room {self.room_number} ({self.room_type})"


class WorkerReport(models.Model):
    """
    Records report of workers related to various Hall of Residences.

    'worker_id' stores the id of the worker. 
    'hall' refers to the related Hall of Residence.
    'worker_name' stores the name of the worker.
    'year' and 'month' stores year and month respectively.
    'absent' stores the number of days a worker was absent in a month.
    'total_day' stores the number of days in a month.
    'remark' stores remarks for a worker.
    """
    worker_id = models.CharField(max_length=10)
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='worker_reports')
    worker_name = models.CharField(max_length=50)
    year =  models.IntegerField(default=2020)
    month = models.IntegerField(default=1)
    absent = models.IntegerField(default= 0)
    total_day = models.IntegerField(default=31)
    remark = models.CharField(max_length=100)
    
    def __str__(self):
        return str(self.worker_name)+'->' + str(self.month) + '-' + str(self.absent)



class HostelInventory(models.Model):
    """
    Model to store hostel inventory information.
    """

    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='inventory')
    item_name = models.CharField(max_length=100)
    quantity = models.PositiveIntegerField(default=0)
    unit_cost = models.DecimalField(max_digits=10, decimal_places=2, default=0)
    remarks = models.TextField(blank=True, null=True)
    last_updated = models.DateTimeField(auto_now=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['hostel', 'item_name']

    def __str__(self):
        return f"{self.hostel.name} - {self.item_name}"


class InventoryItem(models.Model):
    """
    Modern inventory item record.
    """
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='inventory_items', to_field='hall_id')
    name = models.CharField(max_length=100)
    category = models.CharField(max_length=50, choices=InventoryCategory.choices, default=InventoryCategory.OTHER)
    unit = models.CharField(max_length=20, default="pcs")
    expected_quantity = models.PositiveIntegerField(default=0)
    current_quantity = models.PositiveIntegerField(default=0)
    condition = models.CharField(max_length=20, choices=InventoryCondition.choices, default=InventoryCondition.GOOD)
    last_inspected_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hostel_management_inventoryitem'
        ordering = ['hostel', 'category', 'name']
        unique_together = ['hostel', 'name']

    def __str__(self):
        return f"{self.name} at {self.hostel.name}"


class InventoryDiscrepancy(models.Model):
    """
    Records identified discrepancies during inspections.
    """
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='discrepancies')
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, to_field='hall_id')
    discrepancy_type = models.CharField(max_length=20, choices=DiscrepancyType.choices)
    expected_qty = models.PositiveIntegerField()
    actual_qty = models.PositiveIntegerField()
    condition = models.CharField(max_length=20, choices=InventoryCondition.choices, default=InventoryCondition.GOOD)
    remarks = models.TextField()
    reported_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='reported_discrepancies')
    reported_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hostel_management_inventorydiscrepancy'
        ordering = ['-reported_at']


class InventoryAuditLog(models.Model):
    """
    Immutable audit trail for every inventory write.
    """
    item = models.ForeignKey(InventoryItem, on_delete=models.CASCADE, related_name='audit_logs')
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, to_field='hall_id')
    action = models.CharField(max_length=50) # e.g., "Updated", "Inspected"
    old_qty = models.PositiveIntegerField(null=True, blank=True)
    new_qty = models.PositiveIntegerField()
    old_condition = models.CharField(max_length=20, null=True, blank=True)
    new_condition = models.CharField(max_length=20)
    performed_by = models.ForeignKey(User, on_delete=models.CASCADE)
    remarks = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hostel_management_inventoryauditlog'
        ordering = ['-timestamp']

    def delete(self, *args, **kwargs):
        raise PermissionError("InventoryAuditLog entries are immutable and cannot be deleted.")

    def save(self, *args, **kwargs):
        if self.pk:
            raise PermissionError("InventoryAuditLog entries are immutable and cannot be updated.")
        super().save(*args, **kwargs)


class ResourceRequest(models.Model):
    """
    Resource procurement requests submitted by caretakers.
    """
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='resource_requests', to_field='hall_id')
    requested_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='submitted_resource_requests')
    request_type = models.CharField(max_length=20, choices=ResourceRequestType.choices)
    category = models.CharField(max_length=20, choices=InventoryCategory.choices, default=InventoryCategory.OTHER)
    item_name = models.CharField(max_length=100)
    quantity = models.PositiveIntegerField()
    justification = models.TextField()
    status = models.CharField(max_length=20, choices=ResourceRequestStatus.choices, default=ResourceRequestStatus.PENDING)
    reviewed_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='reviewed_resource_requests')
    reviewed_at = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hostel_management_resourcerequest'
        ordering = ['-created_at']
    

# ══════════════════════════════════════════════════════════════
# HM-WF-101: LEAVE MANAGEMENT & ATTENDANCE
# ══════════════════════════════════════════════════════════════

class LeaveRequest(models.Model):
    """
    Leave application entity for managing student leaves.
    
    Supports:
    - BR-HM-101: Active Allotment Prerequisite
    - BR-HM-102: Date Boundary Validation
    - BR-HM-103: Mandatory Justification & Documents
    - BR-HM-104: Role-Based Decision Authority
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='leave_requests')
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='leaves')
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=LeaveStatusChoices.choices,
        default=LeaveStatusChoices.PENDING
    )
    documents = models.FileField(upload_to='hostel/leaves/docs/', null=True, blank=True)
    decision_remarks = models.TextField(null=True, blank=True)
    decided_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='decided_leaves')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hostel_management_leaverequest'
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.student.id.user.username} - {self.start_date} to {self.end_date} ({self.status})"


class StudentAttendanceRecord(models.Model):
    """
    Daily attendance record for students in hostels.
    
    Supports:
    - BR-HM-105: Atomic Synchronization on Leave Approval
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='attendance_records')
    date = models.DateField()
    status = models.CharField(
        max_length=20,
        choices=AttendanceStatus.choices,
        default=AttendanceStatus.NOT_MARKED
    )
    leave_request = models.ForeignKey(LeaveRequest, on_delete=models.SET_NULL, null=True, blank=True, related_name='attendance_entries')

    class Meta:
        db_table = 'hostel_management_studentattendancerecord'
        unique_together = ['student', 'date']
        ordering = ['-date']

    def __str__(self):
        return f"{self.student.id.user.username} - {self.date} ({self.status})"


class HostelComplaint(models.Model):
    """Student complaint model with category routing and escalation.
    
    Supports HM-WF-102: Complaint Resolution Workflow
    - HM-UC-006: Submit Complaint
    - HM-UC-007: Review and Address Complaint
    - HM-UC-008: Escalate Complaint to Warden
    - HM-UC-009: View and Manage Complaint Reports
    
    Enforces:
    - BR-HM-106: Complaint Eligibility Rule
    - BR-HM-107: Complaint Routing by Category
    - BR-HM-108: Mandatory Resolution Remarks
    - BR-HM-109: Escalation Authorization Rule
    - BR-HM-110: Warden Authority on Escalated Complaints
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='hostel_complaints')
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, null=True, blank=True, related_name='complaints')
    category = models.CharField(
        max_length=20,
        choices=ComplaintCategoryChoices.choices,
        default=ComplaintCategoryChoices.OTHER
    )
    description = models.TextField()
    attachments = models.FileField(upload_to='hostel/complaints/', null=True, blank=True)
    status = models.CharField(
        max_length=20,
        choices=ComplaintStatusChoices.choices,
        default=ComplaintStatusChoices.SUBMITTED
    )
    assigned_to_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='assigned_complaints_unified')
    resolution_remarks = models.TextField(blank=True, null=True)
    resolved_by_user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='resolved_complaints')
    resolved_at = models.DateTimeField(null=True, blank=True)
    complaint_uid = models.CharField(max_length=50, unique=True, null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hostel_management_hostelcomplaint'
        ordering = ['-created_at']

    def save(self, *args, **kwargs):
        """Auto-generate complaint UID if not present."""
        if not self.complaint_uid:
            date_str = timezone.now().strftime('%Y%m%d')
            # The actual unique suffix will be handled by the service or we can use a basic one here
            # But UID generation is better in service for atomic sequence
            pass
        super().save(*args, **kwargs)

    @property
    def resolution_notes(self):
        """Alias for resolution_remarks (used by services/serializers)."""
        return self.resolution_remarks
    
    @resolution_notes.setter
    def resolution_notes(self, value):
        self.resolution_remarks = value

    @property
    def warden_assigned(self):
        """Alias for escalated_to (used by services/serializers)."""
        return self.escalated_to
    
    @warden_assigned.setter
    def warden_assigned(self, value):
        self.escalated_to = value

    def __str__(self):
        return f"Complaint {self.complaint_uid or self.id} from {self.student_name} - {self.status}"


class ComplaintHistory(models.Model):
    """Audit trail for complaint status changes and assignments."""
    complaint = models.ForeignKey(HostelComplaint, on_delete=models.CASCADE, related_name='history')
    changed_by = models.ForeignKey(User, on_delete=models.CASCADE)
    old_status = models.CharField(max_length=20, null=True, blank=True)
    new_status = models.CharField(max_length=20)
    remarks = models.TextField(blank=True)
    timestamp = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hostel_management_complainthistory'
        ordering = ['-timestamp']

    def __str__(self):
        return f"{self.complaint.complaint_uid}: {self.old_status} -> {self.new_status} by {self.changed_by}"


class RoomChangeRequest(models.Model):
    """Student room change request model."""
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='room_change_requests')
    current_hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='room_change_from')
    current_room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='room_change_from')
    requested_hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='room_change_to')
    requested_room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True, related_name='room_change_to')
    reason = models.TextField()
    status = models.CharField(
        max_length=20,
        choices=RoomChangeStatusChoices.choices,
        default=RoomChangeStatusChoices.PENDING
    )
    warden_approval = models.BooleanField(default=False)
    warden_remarks = models.TextField(blank=True, null=True)
    approved_by_warden = models.ForeignKey(Faculty, on_delete=models.SET_NULL, null=True, blank=True, related_name='warden_approved_room_changes')
    caretaker_approval = models.BooleanField(default=False)
    caretaker_remarks = models.TextField(blank=True, null=True)
    approved_by_caretaker = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, blank=True, related_name='caretaker_approved_room_changes')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'hostel_management_roomchangerequest'
        ordering = ['-created_at']

    def __str__(self):
        return f"Room Change: {self.student} from Room {self.current_room.room_no} to Room {self.requested_room.room_no if self.requested_room else 'TBD'}"
      
    
class HostelAllotment(models.Model):
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE)
    assignedCaretaker = models.ForeignKey(Staff, on_delete=models.CASCADE ,null=True)
    assignedWarden = models.ForeignKey(Faculty, on_delete=models.CASCADE ,null=True)
    assignedBatch=models.CharField(max_length=50)
    def __str__(self):
        return str(self.hostel)+ str(self.assignedCaretaker)+str(self.assignedWarden) + str(self.assignedBatch)

class StudentDetails(models.Model):
    id = models.CharField(primary_key=True, max_length=20)
    first_name = models.CharField(max_length=100,blank=True,null=True)
    last_name = models.CharField(max_length=100,blank=True,null=True)
    programme = models.CharField(max_length=100,blank=True,null=True)
    batch = models.CharField(max_length=100,blank=True,null=True)
    room_num= models.CharField(max_length=20,blank=True,null=True)
    hall_no= models.CharField(max_length=20,blank=True,null=True)
    hall_id=models.CharField(max_length=20,blank=True,null=True)
    specialization = models.CharField(max_length=100,blank=True,null=True)
    parent_contact = models.CharField(max_length=20, blank=True, null=True)
    address = models.CharField(max_length=255, blank=True, null=True)

    def __str__(self):
      return self.first_name



class GuestRoom(models.Model):
    """
    Registry for rooms designated as Guest Rooms.
    Caretakers add rooms here to make them available for GuestRoomBooking.
    """
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='guest_rooms_registry', to_field='hall_id')
    room = models.OneToOneField(Room, on_delete=models.CASCADE, related_name='guest_room_info')
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hostel_management_guestroom'
        ordering = ['hostel', 'room__room_number']

    def __str__(self):
        return f"Guest Room: {self.hostel.name} - {self.room.room_number}"


class GuestRoomInspection(models.Model):
    """
    Records room inspection results upon guest check-out.
    Mandatory for transition to 'Completed' status.
    """
    booking = models.OneToOneField(GuestRoomBooking, on_delete=models.CASCADE, related_name='inspection')
    conducted_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='inspections_conducted')
    damage_found = models.BooleanField(default=False)
    checklist_json = models.JSONField(default=dict) # e.g. {"walls": "ok", "furniture": "damaged"}
    damage_description = models.TextField(null=True, blank=True)
    damage_photos = models.FileField(upload_to='hostel/guest_rooms/damages/', null=True, blank=True)
    severity = models.CharField(
        max_length=20,
        choices=DamageSeverityChoices.choices,
        null=True, blank=True
    )
    estimated_repair_cost = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    inspection_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = 'hostel_management_guestroominspection'


class GuestRoomPolicy(models.Model):
    """
    Hostel-specific settings for Guest Room bookings.
    """
    hostel = models.OneToOneField(Hostel, on_delete=models.CASCADE, related_name='guest_policy', to_field='hall_id')
    per_night_rate = models.DecimalField(max_digits=10, decimal_places=2, default=500.00)
    max_duration_nights = models.PositiveIntegerField(default=7)
    min_advance_days = models.PositiveIntegerField(default=2)
    max_advance_days = models.PositiveIntegerField(default=30)
    max_concurrent_bookings_per_student = models.PositiveIntegerField(default=3)
    fines_grace_threshold = models.DecimalField(max_digits=10, decimal_places=2, default=0.00) # BR-HM-051.b
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = 'hostel_management_guestroompolicy'

    

# class HostelFine(models.Model):
#     """Fine management model with BR-HM-013 enforcement."""
#     FINE_TYPE_CHOICES = [
#         ('damage', 'Damage'),
#         ('late_fee', 'Late Fee'),
#         ('violation', 'Violation'),
#         ('other', 'Other'),
#     ]
    
#     student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='hostel_fines')
#     hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='fines')
#     student_name = models.CharField(max_length=100)
#     fine_type = models.CharField(max_length=20, choices=FINE_TYPE_CHOICES, default='other')
#     amount = models.DecimalField(max_digits=10, decimal_places=2)
#     status = models.CharField(
#         max_length=20,
#         choices=FineStatusChoices.choices,
#         default=FineStatusChoices.PENDING
#     )
#     reason = models.TextField()
#     issued_date = models.DateField(auto_now_add=True)
#     due_date = models.DateField(null=True, blank=True)
#     issued_by = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, blank=True, related_name='fines_issued')
#     paid_date = models.DateField(null=True, blank=True)
#     waived_by = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, blank=True, related_name='fines_waived')
#     waive_reason = models.TextField(blank=True, null=True)
#     waived_date = models.DateField(null=True, blank=True)
#     created_at = models.DateTimeField(auto_now_add=True)
#     updated_at = models.DateTimeField(auto_now=True)
    
#     class Meta:
#         db_table = 'hostel_management_hostel_fine'
#         ordering = ['-issued_date']

#     def __str__(self):
#         return f"{self.student_name}'s Fine - {self.amount} - {self.status}"
    

class HostelTransactionHistory(models.Model):
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE)
    change_type = models.CharField(max_length=100)  # Example: 'Caretaker', 'Warden', 'Batch'
    previous_value = models.CharField(max_length=255)
    new_value = models.CharField(max_length=255)
    timestamp = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.change_type} change in {self.hostel} at {self.timestamp}"
    
class HostelHistory(models.Model):
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE)
    timestamp = models.DateTimeField(default=timezone.now)
    caretaker = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, related_name='caretaker_history')
    batch = models.CharField(max_length=50, null=True)
    warden = models.ForeignKey(Faculty, on_delete=models.SET_NULL, null=True, related_name='warden_history')

    def __str__(self):
        return f"History for {self.hostel.name} - {self.timestamp}"


# ══════════════════════════════════════════════════════════════
# MISSING CRITICAL MODEL ENUMS (HM-WF-103, 104, 109, 113)
# ══════════════════════════════════════════════════════════════

# Removed legacy RoomAllocationStatusChoices


class AllocationChangeStatusChoices(models.TextChoices):
    """Room allocation change request status."""
    REQUESTED = "requested", "Requested"
    APPROVED_WARDEN = "approved_warden", "Approved by Warden"
    APPROVED_CARETAKER = "approved_caretaker", "Approved by Caretaker"
    REJECTED = "rejected", "Rejected"
    COMPLETED = "completed", "Completed"


class VacationClearanceStatusChoices(models.TextChoices):
    """Room vacation clearance status."""
    REQUESTED = "requested", "Requested"
    VERIFIED = "verified", "Verified by Caretaker"
    COMPLETED = "completed", "Completed by Super Admin"
    REJECTED = "rejected", "Rejected"


class ExtendedStayStatusChoices(models.TextChoices):
    """Extended stay request status."""
    PENDING = "pending", "Pending"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"
    ACTIVE = "active", "Active"
    COMPLETED = "completed", "Completed"


# ══════════════════════════════════════════════════════════════
# HM-WF-103: ACCOMMODATION REQUEST & ALLOTMENT
# ══════════════════════════════════════════════════════════════

class AccommodationApplicationWindow(models.Model):
    """
    Manages the application window during which students can submit accommodation requests.
    - BR-HM-111: BLOCK submission if status ≠ Open
    """
    name = models.CharField(max_length=100)
    start_date = models.DateTimeField()
    end_date = models.DateTimeField()
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)

    def __str__(self):
        return f"{self.name} ({self.start_date.date()} to {self.end_date.date()})"

    @property
    def is_open(self):
        now = timezone.now()
        return self.is_active and self.start_date <= now <= self.end_date


class AccommodationRequest(models.Model):
    """
    Student request for hostel accommodation with preferences.
    """
    class Status(models.TextChoices):
        PENDING = "Pending", "Pending"
        ALLOTTED = "Allotted", "Allotted"
        NOT_ALLOTTED = "NotAllotted", "Not Allotted"

    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='accommodation_requests')
    window = models.ForeignKey(AccommodationApplicationWindow, on_delete=models.CASCADE, related_name='requests')
    preferred_hostel_type = models.CharField(max_length=10, choices=HostelTypeChoices.choices)
    preferred_room_type = models.CharField(max_length=10, choices=RoomTypeChoices.choices)
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.PENDING)
    submitted_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        unique_together = ['student', 'window']
        ordering = ['submitted_at']

    def __str__(self):
        return f"Request by {self.student.id.user.username} - {self.status}"


class RoomAllotment(models.Model):
    """
    Single source of truth for active hostel room assignments.
    - BR-HM-112: never exceed capacity (enforced in view)
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='room_allotments')
    room = models.ForeignKey('Room', on_delete=models.CASCADE, related_name='allotments')
    hostel = models.ForeignKey('Hostel', on_delete=models.CASCADE, related_name='allotments', to_field='hall_id')
    allotted_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='allotments_made')
    allotted_at = models.DateTimeField(auto_now_add=True)
    vacated_at = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        db_table = 'hostel_management_roomallotment'
        # Canonical check for 'student has active hostel allocation'
        # Only one active allotment per student at a time
        constraints = [
            models.UniqueConstraint(
                fields=['student', 'is_active'],
                name='unique_active_allotment',
                condition=models.Q(is_active=True)
            )
        ]
    def __str__(self):
        return f"{self.student.id.user.username} @ {self.hostel.name} - {self.room.room_number}"


# ══════════════════════════════════════════════════════════════
# HM-WF-104: ROOM ALLOCATION CHANGE MODEL
# ══════════════════════════════════════════════════════════════

class RoomAllocationChange(models.Model):
    """
    Room change request model for managing student room change applications.
    
    Supports HM-WF-104: Student Room Change Workflow
    - HM-UC-013: Submit Room Change Request
    - HM-UC-014: Review and Process Room Change Request
    - HM-UC-015: Update Room Allocation and Notify
    
    Enforces:
    - BR-HM-115: Room Change Eligibility Rule
    - BR-HM-116: Dual Approval Requirement
    - BR-HM-117: Occupancy Reconciliation on Room Change
    - BR-HM-118: Mandatory Room Change Notification
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='room_allocation_changes')
    current_room = models.ForeignKey(Room, on_delete=models.CASCADE, related_name='change_requests_from')
    requested_room = models.ForeignKey(Room, on_delete=models.SET_NULL, null=True, blank=True, related_name='change_requests_to')
    reason = models.TextField()
    status = models.CharField(
        max_length=30,
        choices=AllocationChangeStatusChoices.choices,
        default=AllocationChangeStatusChoices.REQUESTED
    )
    requested_date = models.DateField(auto_now_add=True)
    effective_date = models.DateField(null=True, blank=True)
    warden_approval = models.BooleanField(default=False)
    warden_remarks = models.TextField(blank=True, null=True)
    approved_by_warden = models.ForeignKey(Faculty, on_delete=models.SET_NULL, null=True, blank=True, related_name='room_changes_approved_warden')
    warden_approval_date = models.DateTimeField(null=True, blank=True)
    caretaker_approval = models.BooleanField(default=False)
    caretaker_remarks = models.TextField(blank=True, null=True)
    approved_by_caretaker = models.ForeignKey(Staff, on_delete=models.SET_NULL, null=True, blank=True, related_name='room_changes_approved_caretaker')
    caretaker_approval_date = models.DateTimeField(null=True, blank=True)
    rejection_reason = models.TextField(blank=True, null=True)
    completion_date = models.DateField(null=True, blank=True)
    notification_sent = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    class Meta:
        db_table = 'hostel_management_roomallocationchange'
        ordering = ['-requested_date']
    
    def __str__(self):
        return f"Room Change: {self.student.user.username} from {self.current_room.room_number} ({self.status})"

class RoomVacationRequest(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='vacation_requests')
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE)
    vacation_date = models.DateField()
    status = models.CharField(max_length=20, choices=RoomVacationStatusChoices.choices, default="pending")
    remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.student.id.user.username} - {self.room.room_number} ({self.status})"


class ExtendedStayApplication(models.Model):
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='extended_stays')
    room = models.ForeignKey(Room, on_delete=models.CASCADE)
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE)
    start_date = models.DateField()
    end_date = models.DateField()
    reason = models.TextField()
    status = models.CharField(max_length=20, choices=ExtendedStayStatusChoices.choices, default="submitted")
    remarks = models.TextField(blank=True, null=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"Extended Stay: {self.student.user.username} ({self.status})"


# ══════════════════════════════════════════════════════════════
# HM-WF-105: FINE MANAGEMENT MODELS
# ══════════════════════════════════════════════════════════════

class HostelFine(models.Model):
    """
    Model for tracking disciplinary fines imposed on students.
    Supports HM-WF-105: Fine Management Workflow
    """
    student = models.ForeignKey(Student, on_delete=models.CASCADE, related_name='fines')
    hostel = models.ForeignKey(Hostel, on_delete=models.CASCADE, related_name='fines')
    imposed_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='fines_imposed')
    category = models.CharField(max_length=50, choices=FineCategoryChoices.choices)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    reason = models.TextField()
    evidence = models.FileField(upload_to='hostel/fines/evidence/', null=True, blank=True)
    status = models.CharField(max_length=20, choices=FineStatusChoices.choices, default=FineStatusChoices.PENDING)
    imposed_date = models.DateTimeField(auto_now_add=True)
    paid_date = models.DateTimeField(null=True, blank=True)
    fine_uid = models.CharField(max_length=24, unique=True)

    class Meta:
        db_table = 'hostel_management_hostelfine'
        ordering = ['-imposed_date']

    def __str__(self):
        return f"Fine {self.fine_uid} - {self.student.user.username} (₹{self.amount})"

    def save(self, *args, **kwargs):
        if not self.fine_uid:
            # Generate unique ID: FINE-HALL_ID-YYYYMM-XXXX
            import random
            prefix = f"FINE-{self.hostel.hall_id}-{timezone.now().strftime('%y%m')}"
            unique_part = "".join(random.choices("0123456789", k=4))
            self.fine_uid = f"{prefix}-{unique_part}"
        super().save(*args, **kwargs)


class FineExtraDetail(models.Model):
    """
    Extensible storage for category-specific fine details (e.g. damaged item list).
    """
    fine = models.ForeignKey(HostelFine, on_delete=models.CASCADE, related_name='extra_details')
    detail_type = models.CharField(max_length=50)
    detail_json = models.JSONField()

    class Meta:
        db_table = 'hostel_management_fineextradetail'

    def __str__(self):
        return f"Details for {self.fine.fine_uid} ({self.detail_type})"
"""
Hostel Management Selectors

This module contains ALL database queries for the hostel_management app.
NO queries are allowed in views or services.

Query patterns:
- get_*: Returns single object or None
- list_*: Returns QuerySet for lists
- filter_*: Returns QuerySet with specific filters
- count_*: Returns count of objects
"""

from django.db import transaction, models
from django.db.models import Q, Count, F, Sum
from django.db.models.functions import TruncMonth
from django.utils import timezone
from datetime import timedelta

from .models import (
    LeaveRequest, StudentAttendanceRecord, HostelComplaint,
    RoomAllocationChange, HostelFine,
    StaffSchedule, HostelInventory, HostelNoticeBoard,
    GuestRoom, GuestRoomBooking, HostelTransactionHistory,
    WorkerReport, HallWarden,
    HallCaretaker, StudentDetails, LeaveStatusChoices, ComplaintStatusChoices,
    ComplaintPriorityChoices, FineStatusChoices, AccommodationApplicationWindow,
    AccommodationRequest, RoomAllotment,
    Hostel, Room, HostelStaffAssignment,
    InventoryItem, InventoryDiscrepancy,
    InventoryAuditLog, ResourceRequest, Notice,
    NoticeReadStatus, NoticeStatus, SecurityGuard, GuardShift,
    ShiftScheduleLog
)
from applications.academic_information.models import Student
from applications.globals.models import Staff


def get_student_by_roll(roll_number):
    """Fetch student details by roll number."""
    return Student.objects.filter(id__id=roll_number).select_related('id__user').first()


# ══════════════════════════════════════════════════════════════
# HALL & INFRASTRUCTURE QUERIES
# ══════════════════════════════════════════════════════════════

def get_hostel_by_id(hall_id):
    """Get a single hostel by hall_id string."""
    return Hostel.objects.filter(hall_id=hall_id).first()

def list_rooms_by_hostel(hall_id):
    """Get all rooms for a hostel."""
    return Room.objects.filter(hostel_id=hall_id).order_by('floor', 'room_number')


def get_all_hostels():
    """Get all hostels."""
    return Hostel.objects.all().order_by('hall_id')


def list_active_hostels():
    """Get all active hostels."""
    # Hostel status is managed via status field
    return Hostel.objects.all().order_by('hall_id')


def get_room(hall_id, room_number):
    """Get a specific room in a hostel."""
    return Room.objects.filter(
        hostel__hall_id=hall_id,
        room_number=room_number
    ).first()


def get_hostel_rooms(hall_id):
    """Get all rooms in a hostel."""
    return Room.objects.filter(hostel__hall_id=hall_id).order_by('floor', 'room_number')


def list_available_rooms(hall_id):
    """Get available rooms in a hall."""
    return Room.objects.filter(
        hostel__hall_id=hall_id,
        status='available'
    ).order_by('floor', 'room_number')


def list_rooms_by_status(hall_id, status):
    """Get rooms by status in a hall."""
    return Room.objects.filter(
        hostel__hall_id=hall_id,
        status=status
    )


def get_hostel_staff(hall_id, role=None):
    """Get staff assignments for a hostel."""
    queryset = HostelStaffAssignment.objects.filter(hostel__hall_id=hall_id, is_active=True)
    if role:
        queryset = queryset.filter(role=role)
    return queryset


def list_hostel_wardens(hall_id):
    """Get active wardens for a hostel."""
    from .models import StaffRoleChoices
    return HostelStaffAssignment.objects.filter(
        hostel__hall_id=hall_id,
        role=StaffRoleChoices.WARDEN,
        is_active=True
    ).select_related('user')

def get_hostel_warden(hall_id):
    """Get the primary active warden for a hostel."""
    return list_hostel_wardens(hall_id).first()

def list_hostel_caretakers(hall_id):
    """Get active caretakers for a hostel."""
    from .models import StaffRoleChoices
    return HostelStaffAssignment.objects.filter(
        hostel__hall_id=hall_id,
        role=StaffRoleChoices.CARETAKER,
        is_active=True
    ).select_related('user')

def get_hostel_caretaker(hall_id):
    """Get the primary active caretaker for a hostel."""
    return list_hostel_caretakers(hall_id).first()


# ══════════════════════════════════════════════════════════════
# STUDENT & USER QUERIES
# ══════════════════════════════════════════════════════════════

def get_student(user):
    """
    Get a student by their user object or user ID.
    Supports both standard Django User and custom Fusion user ID patterns.
    """
    if hasattr(user, 'id'):
        return Student.objects.filter(id__user=user).first()
    # If a string/integer ID is passed
    return Student.objects.filter(id__user_id=user).first() or Student.objects.filter(id__id=user).first()


def get_staff(user):
    """Get a staff instance by user object or user ID."""
    if hasattr(user, 'id'):
        return Staff.objects.filter(id__user=user).first()
    return Staff.objects.filter(id__user_id=user).first()


def get_faculty(user):
    """Get a faculty instance by user object or user ID."""
    from applications.globals.models import Faculty
    if hasattr(user, 'id'):
        return Faculty.objects.filter(id__user=user).first()
    return Faculty.objects.filter(id__user_id=user).first()


def is_user_warden(user):
    """
    Checks if a user is a Warden (Modern or Legacy).
    1. Modern check: HostelStaffAssignment
    2. Legacy check: HallWarden / Faculty assignment
    """
    if not (user and user.is_authenticated):
        return False
    
    from .models import StaffRoleChoices
    # 1. Modern assignment
    if HostelStaffAssignment.objects.filter(user=user, role=StaffRoleChoices.WARDEN, is_active=True).exists():
        return True
        
    # 2. Legacy assignment via HallWarden
    faculty = get_faculty(user)
    if faculty and HallWarden.objects.filter(faculty=faculty, is_active=True).exists():
        return True
        
    return False


def is_user_caretaker(user):
    """
    Checks if a user is a Caretaker (Modern or Legacy).
    1. Modern check: HostelStaffAssignment
    2. Legacy check: HallCaretaker / Staff assignment
    """
    if not (user and user.is_authenticated):
        return False
        
    from .models import StaffRoleChoices
    # 1. Modern assignment
    if HostelStaffAssignment.objects.filter(user=user, role=StaffRoleChoices.CARETAKER, is_active=True).exists():
        return True
        
    # 2. Legacy assignment via HallCaretaker
    staff = get_staff(user)
    if staff and HallCaretaker.objects.filter(staff=staff, is_active=True).exists():
        return True
        
    return False


def is_user_warden_or_caretaker(user):
    """Checks if user has any specialized hostel staff role."""
    return is_user_warden(user) or is_user_caretaker(user)


def list_user_staff_assignments(user, role=None):
    """Get all staff assignments for a specific user."""
    from .models import HostelStaffAssignment
    queryset = HostelStaffAssignment.objects.filter(user=user, is_active=True)
    if role:
        queryset = queryset.filter(role=role)
    return queryset


def list_assigned_hostels(user):
    """
    Returns a QuerySet of all Hostels the user is authorized to manage.
    Supports both Modern and Legacy assignments.
    """
    if not (user and user.is_authenticated):
        return Hostel.objects.none()

    # 1. Modern Assignments
    modern_hostel_ids = list(HostelStaffAssignment.objects.filter(
        user=user, is_active=True
    ).values_list('hostel_id', flat=True))

    # 2. Legacy Assignments
    legacy_hall_ids = []
    
    faculty = get_faculty(user)
    if faculty:
        legacy_hall_ids.extend(list(HallWarden.objects.filter(
            faculty=faculty, is_active=True
        ).values_list('hall_id', flat=True)))
        
    staff = get_staff(user)
    if staff:
        legacy_hall_ids.extend(list(HallCaretaker.objects.filter(
            staff=staff, is_active=True
        ).values_list('hall_id', flat=True)))

    if not legacy_hall_ids and not modern_hostel_ids:
        return Hostel.objects.none()

    # Create robust query for hostels
    query = Q(hall_id__in=modern_hostel_ids)
    
    if legacy_hall_ids:
        import re
        for l_id in set(legacy_hall_ids):
            digits = re.findall(r'\d+', str(l_id))
            if digits:
                for digit in digits:
                    query |= Q(hall_id__icontains=digit) | Q(name__icontains=digit)
            else:
                query |= Q(hall_id__icontains=str(l_id)) | Q(name__icontains=str(l_id))

    return Hostel.objects.filter(query).distinct()


def list_students_by_academic_batch(batch_id):
    """Get all students belonging to a specific academic batch (for bulk allocation)."""
    return Student.objects.filter(
        batch_id=batch_id
    ).select_related(
        'id__user',
        'batch_id__discipline'
    ).order_by('id__user__username')


# ══════════════════════════════════════════════════════════════
# HM-WF-101: LEAVE QUERIES
# ══════════════════════════════════════════════════════════════

def get_student_leave(leave_id):
    """Get a specific leave record."""
    return LeaveRequest.objects.filter(id=leave_id).first()


def get_student_current_leave(student_id, start_date, end_date):
    """Check if student has overlapping leave in date range."""
    return LeaveRequest.objects.filter(
        student_id=student_id,
        status=LeaveStatusChoices.APPROVED,
        start_date__lt=end_date,
        end_date__gte=start_date
    ).first()


def list_student_leaves(student):
    """Get all leaves for a student."""
    return LeaveRequest.objects.filter(
        student=student
    ).order_by('-created_at')


def list_pending_leaves():
    """Get all pending leaves."""
    return LeaveRequest.objects.filter(
        status=LeaveStatusChoices.PENDING
    ).order_by('-created_at')


def list_pending_leaves_by_hall(hall_id):
    """Get pending leaves for students in a specific hostel."""
    return LeaveRequest.objects.filter(
        status=LeaveStatusChoices.PENDING,
        student__room_allotments__hostel__hall_id=hall_id,
        student__room_allotments__is_active=True
    ).distinct().order_by('-created_at')


def count_student_approved_leaves(student_id, year=None):
    """Count approved leaves for a student in a year."""
    query = LeaveRequest.objects.filter(
        student_id=student_id,
        status=LeaveStatusChoices.APPROVED
    )
    if year:
        query = query.filter(start_date__year=year)
    return query.count()


def list_student_leaves_by_status(student_id, status):
    """Get leaves for a student by status."""
    return LeaveRequest.objects.filter(
        student_id=student_id,
        status=status
    ).order_by('-created_at')


def list_leaves_requiring_attendance_update(start_date, end_date):
    """Get approved leaves in date range requiring attendance marking."""
    return LeaveRequest.objects.filter(
        status=LeaveStatusChoices.APPROVED,
        start_date__lte=end_date,
        end_date__gte=start_date
    )


# ══════════════════════════════════════════════════════════════
# HM-WF-102: COMPLAINT QUERIES
# ══════════════════════════════════════════════════════════════

def get_complaint(complaint_id):
    """Get a specific complaint."""
    return HostelComplaint.objects.filter(id=complaint_id).first()


def list_student_complaints(student):
    """Get all complaints from a student."""
    return HostelComplaint.objects.filter(
        student=student
    ).order_by('-created_at')


def list_open_complaints():
    """Get all open/submitted complaints."""
    return HostelComplaint.objects.filter(
        status=ComplaintStatusChoices.SUBMITTED
    ).order_by('-created_at')


def list_complaints_by_status(status):
    """Get complaints by status."""
    return HostelComplaint.objects.filter(
        status=status
    ).order_by('-created_at')


def list_complaints_by_category(category):
    """Get complaints by category."""
    return HostelComplaint.objects.filter(
        category=category
    ).order_by('-created_at')


def list_complaints_by_hall(hall_id):
    """Get complaints in a specific hostel."""
    return HostelComplaint.objects.filter(
        hostel__hall_id=hall_id
    ).order_by('-created_at')


def list_complaints_assigned_to_user(user_id):
    """Get complaints assigned to a specific user (staff/warden)."""
    return HostelComplaint.objects.filter(
        assigned_to_user_id=user_id
    ).exclude(status=ComplaintStatusChoices.CLOSED).order_by('-created_at')


def list_escalated_complaints():
    """Get complaints escalated to warden."""
    return HostelComplaint.objects.filter(
        status=ComplaintStatusChoices.ESCALATED
    ).order_by('-created_at')


def list_escalated_complaints_for_warden(faculty_id):
    """Get escalated complaints assigned to a warden."""
    return HostelComplaint.objects.filter(
        escalated_to_warden=True,
        escalated_to_id=faculty_id
    ).exclude(status=ComplaintStatusChoices.CLOSED).order_by('-created_at')


def count_open_complaints_for_student(student_id):
    """Count open complaints for a student."""
    return HostelComplaint.objects.filter(
        student_id=student_id,
        status__in=[ComplaintStatusChoices.SUBMITTED, ComplaintStatusChoices.UNDER_REVIEW]
    ).count()


def list_complaints_by_priority(priority):
    """Get complaints by priority level."""
    return HostelComplaint.objects.filter(
        priority=priority
    ).order_by('-created_at')


def list_high_priority_open_complaints():
    """Get high priority and critical open complaints."""
    return HostelComplaint.objects.filter(
        status=ComplaintStatusChoices.SUBMITTED,
        priority__in=[ComplaintPriorityChoices.HIGH, ComplaintPriorityChoices.CRITICAL]
    ).order_by('-created_at')


# ══════════════════════════════════════════════════════════════
# HM-WF-103 & HM-WF-104: ROOM ALLOCATION QUERIES
# ══════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════
# HM-WF-103: ACCOMMODATION SELECTORS
# ══════════════════════════════════════════════════════════════

def get_active_application_window():
    """Get the currently active application window."""
    now = timezone.now()
    return AccommodationApplicationWindow.objects.filter(
        is_active=True,
        start_date__lte=now,
        end_date__gte=now
    ).first()


def list_all_application_windows():
    """List all application windows."""
    return AccommodationApplicationWindow.objects.all().order_by('-start_date')


def get_accommodation_request(request_id):
    """Get a specific accommodation request."""
    return AccommodationRequest.objects.filter(id=request_id).first()


def list_pending_requests(window_id=None):
    """List pending accommodation requests, optionally filtered by window."""
    query = AccommodationRequest.objects.filter(status=AccommodationRequest.Status.PENDING)
    if window_id:
        query = query.filter(window_id=window_id)
    return query.select_related('student__id__user', 'window').order_by('-submitted_at')


def get_student_accommodation_request(student, window):
    """Get a student's request for a specific window."""
    return AccommodationRequest.objects.filter(student=student, window=window).first()


def get_active_allotment_by_student(student):
    """
    Get student's current active room allotment.
    FALLBACK: If no record in RoomAllotment, checks legacy hall_no/room_no in Student profile.
    """
    # 1. Try modern system (RoomAllotment)
    allotment = RoomAllotment.objects.filter(
        student=student,
        is_active=True
    ).select_related('room', 'hostel').first()

    if allotment:
        return allotment

    # 2. Fallback to legacy models (Student academic info or StudentDetails hostel info)
    legacy_hall = None
    legacy_room = ""

    # Check academic Student fields first
    if student:
        # hall_no is often an integer or a string like "4" or "H-4"
        if hasattr(student, 'hall_no') and student.hall_no:
            legacy_hall = str(student.hall_no)
        if hasattr(student, 'room_no') and student.room_no:
            legacy_room = str(student.room_no)

    # If no data in academic Student, check hostel StudentDetails (Hostel model)
    if not legacy_hall and student:
        details = StudentDetails.objects.filter(id=student.id.id).first()
        if details:
            legacy_hall = details.hall_id or details.hall_no
            legacy_room = details.room_num or legacy_room

    if legacy_hall or legacy_room:
        # Try to find a matching Hostel object for name resolution
        hostel = None
        if legacy_hall:
            import re
            hall_digits = re.findall(r'\d+', str(legacy_hall))
            
            hostel_query = Q()
            if hall_digits:
                for digit in hall_digits:
                    # Specific naming like hall4 or Hall 4
                    hostel_query |= Q(hall_id__icontains=digit) | Q(name__icontains=digit)
            else:
                hostel_query = Q(hall_id__icontains=str(legacy_hall)) | Q(name__icontains=str(legacy_hall))

            hostel = Hostel.objects.filter(hostel_query).first()

        if hostel or legacy_room:
            # Return a "Virtual Allotment" object for the serializer
            # Needs to mimic RoomAllotment attributes expected by RoomAllotmentSerializer
            class VirtualAllotment:
                def __init__(self, h, r, s, lh):
                    self._is_virtual = True
                    self.is_legacy = True # Flag for UI to show "Legacy Allocation"
                    self.id = f"legacy-{s.pk if s else 'unknown'}"
                    self.hostel = h
                    # Fallback name if Hostel object not found
                    self.hostel_name = h.name if h else f"Hall {lh}" 
                    self.room = type('RoomMock', (object,), {'room_number': r or 'N/A'})
                    self.student = s
                    self.is_active = True
                    self.allotted_at = getattr(s, 'created_at', timezone.now() if s else timezone.now())
                    self.vacated_at = None

            return VirtualAllotment(hostel, str(legacy_room), student, legacy_hall)

    return None


def get_active_allotment_by_student(student):
    """Get the current active allotment for a student."""
    return RoomAllotment.objects.filter(
        student=student,
        is_active=True
    ).select_related('hostel', 'room').first()

def list_allotments_by_hostel(hostel_id):
    """List active allotments for a hostel."""
    return RoomAllotment.objects.filter(
        hostel_id=hostel_id,
        is_active=True
    ).select_related('student__id__user', 'room')


def list_active_room_allotments(hall_id=None):
    """List all active room allotments, optionally filtered by hall."""
    query = RoomAllotment.objects.filter(is_active=True)
    if hall_id:
        query = query.filter(hostel__hall_id=hall_id)
    return query.select_related('student__id__user', 'room', 'hostel').order_by('hostel__hall_id', 'room__room_number')


def list_available_rooms_for_allotment(hostel_type, room_type):
    """
    Find rooms with available capacity based on preferences.
    """
    return Room.objects.filter(
        hostel__type=hostel_type,
        capacity__gt=F('current_occupancy'),
        status='Available'
    ).select_related('hostel').order_by('hostel__name', 'room_number')


def get_hostel_capacity_dashboard():
    """Get capacity overview for all hostels."""
    return Hostel.objects.annotate(
        occupied_seats=Sum('rooms_setup__current_occupancy'),
        available_seats=F('total_capacity') - Sum('rooms_setup__current_occupancy')
    )


# ══════════════════════════════════════════════════════════════
# HM-WF-104: ROOM CHANGE QUERIES
# ══════════════════════════════════════════════════════════════

def list_room_changes_by_student(student):
    """Get all room change requests for a student."""
    return RoomAllocationChange.objects.filter(
        student=student
    ).order_by('-requested_date')


def get_room_change(change_id):
    """Get a specific room change request."""
    return RoomAllocationChange.objects.filter(id=change_id).first()


def list_pending_room_changes():
    """Get all pending room change requests."""
    from .models import AllocationChangeStatusChoices
    return RoomAllocationChange.objects.filter(
        status=AllocationChangeStatusChoices.REQUESTED
    ).order_by('-requested_date')


def list_room_changes_by_status(status):
    """Get room changes by status."""
    return RoomAllocationChange.objects.filter(
        status=status
    ).order_by('-requested_date')


def list_room_changes_for_warden(faculty_id):
    """Get room changes pending warden approval."""
    from .models import AllocationChangeStatusChoices
    return RoomAllocationChange.objects.filter(
        status=AllocationChangeStatusChoices.REQUESTED
    ).select_related('student', 'current_room', 'requested_room').order_by('-requested_date')


def list_room_changes_for_caretaker(staff_id):
    """Get room changes pending caretaker approval."""
    from .models import AllocationChangeStatusChoices
    return RoomAllocationChange.objects.filter(
        status=AllocationChangeStatusChoices.APPROVED_WARDEN
    ).select_related('student', 'current_room', 'requested_room').order_by('-requested_date')


def get_all_room_changes():
    """Get all room changes."""
    return RoomAllocationChange.objects.all().order_by('-requested_date')


def get_student_room_changes(user):
    """Get all room changes for a student user."""
    student = get_student(user)
    if not student:
        return RoomAllocationChange.objects.none()
    return list_room_changes_by_student(student)


# ══════════════════════════════════════════════════════════════
# HM-WF-105: FINE QUERIES
# ══════════════════════════════════════════════════════════════

def get_fine(fine_id):
    """Get a specific fine record."""
    return HostelFine.objects.filter(id=fine_id).first()


def list_student_fines(student):
    """Get all fines for a student."""
    return HostelFine.objects.filter(
        student=student
    ).order_by('-issued_date')


def list_student_pending_fines(student):
    """Get unpaid fines for a student."""
    from .models import FineStatusChoices
    return HostelFine.objects.filter(
        student=student,
        status=FineStatusChoices.PENDING
    ).order_by('-due_date')


def list_pending_fines():
    """Get all pending fines."""
    from .models import FineStatusChoices
    return HostelFine.objects.filter(
        status=FineStatusChoices.PENDING
    ).order_by('-due_date')


def list_overdue_fines():
    """Get overdue fines (past due date and still pending)."""
    from .models import FineStatusChoices
    return HostelFine.objects.filter(
        status=FineStatusChoices.PENDING,
        due_date__lt=timezone.now().date()
    ).order_by('-due_date')


def list_fines_by_type(fine_type):
    """Get fines by type."""
    return HostelFine.objects.filter(
        fine_type=fine_type
    ).order_by('-issued_date')


def list_fines_by_hall(hall_id):
    """Get all fines issued in a hostel."""
    return HostelFine.objects.filter(
        hostel__hall_id=hall_id
    ).order_by('-issued_date')


def sum_student_fines(student_id, status=None):
    """Get total fine amount for a student."""
    from .models import FineStatusChoices
    query = HostelFine.objects.filter(student_id=student_id)
    if status:
        query = query.filter(status=status)
    else:
        query = query.exclude(status=FineStatusChoices.CANCELLED)
    result = query.aggregate(total=Sum('amount'))
    return result['total'] or 0


def count_student_unpaid_fines(student_id):
    """Count unpaid fines for a student."""
    from .models import FineStatusChoices
    return HostelFine.objects.filter(
        student_id=student_id,
        status=FineStatusChoices.PENDING
    ).count()


def list_fines_issued_by_staff(staff_id):
    """Get fines issued by a specific staff member."""
    return HostelFine.objects.filter(
        issued_by_id=staff_id
    ).order_by('-issued_date')


# ══════════════════════════════════════════════════════════════
# HM-WF-107: STAFF SCHEDULE QUERIES
# ══════════════════════════════════════════════════════════════

def get_staff_schedule(schedule_id):
    """Get a specific staff schedule."""
    return StaffSchedule.objects.filter(id=schedule_id).first()


def list_hall_schedules(hall_id):
    """Get all schedules for a hostel."""
    return StaffSchedule.objects.filter(
        hostel__hall_id=hall_id
    ).order_by('day_of_week', 'start_time')


def list_staff_schedules(staff_id):
    """Get all schedules for a staff member."""
    return StaffSchedule.objects.filter(
        staff_id=staff_id
    ).order_by('day_of_week', 'start_time')


def get_staff_schedule_by_day(hall_id, staff_id, day):
    """Get staff schedule for a specific day in a hall."""
    return StaffSchedule.objects.filter(
        hostel__hall_id=hall_id,
        staff_id=staff_id,
        day_of_week=day
    ).first()


def list_schedules_by_day(hall_id, day):
    """Get all schedules for a specific day in a hall."""
    return StaffSchedule.objects.filter(
        hostel__hall_id=hall_id,
        day_of_week=day
    ).order_by('start_time')


# ══════════════════════════════════════════════════════════════
# HM-WF-108: INVENTORY QUERIES
# ══════════════════════════════════════════════════════════════

def get_inventory_item(inventory_id):
    """Get a specific inventory item."""
    return HostelInventory.objects.filter(id=inventory_id).first()


def list_hall_inventory(hall_id):
    """Get all inventory for a hostel."""
    return HostelInventory.objects.filter(
        hostel__hall_id=hall_id
    ).order_by('item_name')


def get_inventory_by_name(hall_id, item_name):
    """Get inventory item by name in a hall."""
    return HostelInventory.objects.filter(
        hostel__hall_id=hall_id,
        item_name=item_name
    ).first()


def list_low_stock_inventory(hall_id, threshold=5):
    """Get inventory items below threshold."""
    return HostelInventory.objects.filter(
        hostel__hall_id=hall_id,
        quantity__lt=threshold
    ).order_by('quantity')


# ══════════════════════════════════════════════════════════════
# SECURITY MANAGEMENT QUERIES
# ══════════════════════════════════════════════════════════════

def list_security_guards(is_active=True):
    """List all security guards."""
    return SecurityGuard.objects.filter(is_active=is_active)


def get_security_guard(guard_id):
    """Fetch a security guard by ID."""
    return SecurityGuard.objects.filter(id=guard_id).first()


def list_guard_shifts(hostel_id=None, date=None, guard_id=None):
    """
    List guard shifts with optional filtering.
    """
    qs = GuardShift.objects.all().select_related('guard', 'hostel', 'assigned_by')
    if hostel_id:
        qs = qs.filter(hostel_id=hostel_id)
    if date:
        qs = qs.filter(date=date)
    if guard_id:
        qs = qs.filter(guard_id=guard_id)
    return qs


def check_guard_shift_conflict(guard_id, date, start_time, end_time, exclude_id=None):
    """
    Checks if a guard has an overlapping shift on a given date.
    Returns True if conflict exists, False otherwise.
    BR-HM-016.a Enforcement Helper.
    """
    overlap_qs = GuardShift.objects.filter(
        guard_id=guard_id,
        date=date
    ).filter(
        Q(start_time__lt=end_time, end_time__gt=start_time)
    )
    
    if exclude_id:
        overlap_qs = overlap_qs.exclude(id=exclude_id)
        
    return overlap_qs.exists()


def list_shift_audit_logs(hostel_id=None):
    """List immutable shift schedule logs."""
    qs = ShiftScheduleLog.objects.all().select_related('guard', 'hostel', 'performed_by')
    if hostel_id:
        qs = qs.filter(hostel_id=hostel_id)
    return qs


def get_security_deployment_summary(hostel_id, date=None):
    """
    Aggregates current deployment data for the dashboard.
    """
    if not date:
        date = timezone.now().date()
        
    shifts = list_guard_shifts(hostel_id=hostel_id, date=date)
    
    # Filter guards by hostel to show unassigned guards FOR THIS HOSTEL
    total_guards = SecurityGuard.objects.filter(hostel_id=hostel_id, is_active=True).count()
    assigned_count = shifts.values('guard').distinct().count()
    
    return {
        'total_shifts': shifts.count(),
        'assigned_guards': assigned_count,
        'unassigned_guards': max(0, total_guards - assigned_count),
        'shifts_by_type': list(shifts.values('shift_type').annotate(count=Count('id')))
    }


def list_student_fines_by_status(student_id, status):
    """Get student fines filtered by status."""
    return HostelFine.objects.filter(
        student_id=student_id,
        status=status
    ).order_by('-issued_date')


def get_student_complaints_by_status(student_id, statuses):
    """Get student complaints filtered by list of statuses."""
    return HostelComplaint.objects.filter(
        student_id=student_id,
        status__in=statuses
    ).order_by('-created_at')


# ══════════════════════════════════════════════════════════════
# HM-WF-110: NOTICE BOARD QUERIES
# ══════════════════════════════════════════════════════════════

def get_notice(notice_id):
    """Get a specific notice."""
    return HostelNoticeBoard.objects.filter(id=notice_id).first()


def list_active_notices(hall_id):
    """
    Get all active notices for a hostel.
    """
    from django.db.models import Case, When, Value, IntegerField
    
    return HostelNoticeBoard.objects.filter(
        hostel__hall_id=hall_id,
        is_active=True
    ).annotate(
        priority=Case(
            When(title__icontains='urgent', then=Value(1)),
            When(title__icontains='important', then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        )
    ).order_by('priority', '-posted_date')


def list_all_notices(hall_id):
    """Get all notices (active and archived) for a hall."""
    from django.db.models import Case, When, Value, IntegerField
    
    return HostelNoticeBoard.objects.filter(
        hostel__hall_id=hall_id
    ).annotate(
        priority=Case(
            When(title__icontains='urgent', then=Value(1)),
            When(title__icontains='important', then=Value(2)),
            default=Value(3),
            output_field=IntegerField(),
        )
    ).order_by('priority', '-posted_date')


def list_notices_by_poster(user_id):
    """Get notices posted by a user."""
    return HostelNoticeBoard.objects.filter(
        posted_by_id=user_id
    ).order_by('-posted_date')


# ══════════════════════════════════════════════════════════════
# HM-WF-112: GUEST ROOM SELECTORS (CHUNK 12)
# ══════════════════════════════════════════════════════════════

def get_guest_room(guest_room_id):
    """Fetch a guest room entry by ID."""
    return GuestRoom.objects.filter(id=guest_room_id).select_related('room', 'hostel').first()


def list_guest_rooms_registry(hall_id=None):
    """List all rooms in the guest registry."""
    queryset = GuestRoom.objects.filter(is_active=True).select_related('room', 'hostel')
    if hall_id:
        queryset = queryset.filter(hostel__hall_id=hall_id)
    return queryset


def get_guest_room_availability(guest_room_id, start_date, end_date, exclude_booking_id=None):
    """
    Check if a specifically registered guest room is available for a date range.
    Returns False if overlapping active/checked-in booking exists.
    """
    from .models import BookingStatusChoices
    
    overlaps = GuestRoomBooking.objects.filter(
        room__guest_room_info__id=guest_room_id, # Link via Room -> GuestRoom
        status__in=[BookingStatusChoices.APPROVED, BookingStatusChoices.CHECKED_IN],
        check_in_date__lt=end_date,
        check_out_date__gt=start_date
    )
    
    if exclude_booking_id:
        overlaps = overlaps.exclude(id=exclude_booking_id)
        
    return not overlaps.exists()


def list_available_rooms_for_guest_designation(hall_id):
    """List rooms in a hostel that are NOT currently in the GuestRoom registry."""
    registered_room_ids = GuestRoom.objects.filter(
        hostel__hall_id=hall_id, is_active=True
    ).values_list('room_id', flat=True)
    
    return Room.objects.filter(
        hostel__hall_id=hall_id,
        current_occupancy=0,
        status='Available'
    ).exclude(id__in=registered_room_ids).order_by('room_number')


def get_guest_booking(booking_id):
    """Fetch guest booking with related data."""
    return GuestRoomBooking.objects.filter(id=booking_id).select_related(
        'student__id__user', 'room', 'hostel'
    ).first()


def get_guest_booking_by_uid(booking_uid):
    """Fetch guest booking by public UID."""
    return GuestRoomBooking.objects.filter(booking_uid=booking_uid).select_related(
        'student__id__user', 'room', 'hostel'
    ).first()


def list_student_guest_bookings(student):
    """List guest bookings for a specific student."""
    return GuestRoomBooking.objects.filter(student=student).order_by('-created_at')


def list_pending_guest_bookings(hall_ids=None):
    """List pending bookings for Caretaker review."""
    from .models import BookingStatusChoices
    queryset = GuestRoomBooking.objects.filter(
        status=BookingStatusChoices.PENDING
    ).select_related('student__id__user', 'room', 'hostel')
    
    if hall_ids:
        queryset = queryset.filter(hostel__hall_id__in=hall_ids)
    return queryset.order_by('check_in_date')


def list_guest_bookings_scoped(user, filters=None):
    """
    List bookings based on user role and filters.
    """
    
    if user.is_superuser:
        queryset = GuestRoomBooking.objects.all()
    elif is_user_warden_or_caretaker(user):
        assigned_hostels = list_assigned_hostels(user).values_list('hall_id', flat=True)
        queryset = GuestRoomBooking.objects.filter(hostel__hall_id__in=assigned_hostels)
    else:
        student = get_student(user)
        queryset = GuestRoomBooking.objects.filter(student=student)

    if filters:
        if 'status' in filters:
            queryset = queryset.filter(status=filters['status'])
        if 'hostel' in filters:
            queryset = queryset.filter(hostel__hall_id=filters['hostel'])

    return queryset.select_related('student__id__user', 'room', 'hostel').order_by('-created_at')


def get_guest_policy(hall_id):
    """Fetch the guest policy for a specific hostel."""
    from .models import GuestRoomPolicy
    return GuestRoomPolicy.objects.filter(hostel__hall_id=hall_id).first()


def get_guest_inspection(booking_id):
    """Fetch inspection result for a booking."""
    from .models import GuestRoomInspection
    return GuestRoomInspection.objects.filter(booking_id=booking_id).first()


# ══════════════════════════════════════════════════════════════
# ATTENDANCE & TRANSACTION TRACKING QUERIES
# ══════════════════════════════════════════════════════════════

def get_attendance_record(attendance_id):
    """Get a specific attendance record."""
    return StudentAttendanceRecord.objects.filter(id=attendance_id).first()


def list_student_attendance(student_id, days=30):
    """Get attendance records for a student in last X days."""
    start_date = timezone.now().date() - timedelta(days=days)
    return StudentAttendanceRecord.objects.filter(
        student_id=student_id,
        date__gte=start_date
    ).order_by('-date')


def list_attendance_by_date(hall_id, date):
    """Get attendance records for a hostel on a specific date."""
    return StudentAttendanceRecord.objects.filter(
        student__room_allotments__hostel__hall_id=hall_id,
        date=date
    ).order_by('student__id__user__username')


def list_date_attendance_range(hall_id, start_date, end_date):
    """Get attendance records for a date range."""
    return StudentAttendanceRecord.objects.filter(
        student__room_allotments__hostel__hall_id=hall_id,
        date__range=[start_date, end_date]
    ).order_by('-date', 'student__id__user__username')


def get_hostel_attendance_summary(hall_id):
    """
    Get attendance summary for all students in a hostel.
    Returns queryset with statistics per student.
    """
    from .models import AttendanceStatus
    
    # Get students currently allotted to this hostel
    allotted_students = Student.objects.filter(
        room_allotments__hostel__hall_id=hall_id,
        room_allotments__is_active=True
    ).select_related('id__user')

    return allotted_students.annotate(
        present_count=Count('attendance_records', filter=Q(attendance_records__status=AttendanceStatus.PRESENT)),
        absent_count=Count('attendance_records', filter=Q(attendance_records__status=AttendanceStatus.ABSENT)),
        on_leave_count=Count('attendance_records', filter=Q(attendance_records__status=AttendanceStatus.ON_LEAVE))
    ).order_by('id__user__username')


def get_student_attendance_stats(student_id):
    """Get attendance statistics for a single student."""
    from .models import AttendanceStatus
    return StudentAttendanceRecord.objects.filter(student_id=student_id).aggregate(
        present_count=Count('id', filter=Q(status=AttendanceStatus.PRESENT)),
        absent_count=Count('id', filter=Q(status=AttendanceStatus.ABSENT)),
        on_leave_count=Count('id', filter=Q(status=AttendanceStatus.ON_LEAVE))
    )


def list_student_absences(student_id):
    """List all dates where a student was marked absent."""
    from .models import AttendanceStatus
    return StudentAttendanceRecord.objects.filter(
        student_id=student_id,
        status=AttendanceStatus.ABSENT
    ).order_by('-date')


def get_transaction_history(transaction_id):
    """Get a specific transaction history record."""
    return HostelTransactionHistory.objects.filter(id=transaction_id).first()


def list_hall_transactions(hall_id):
    """Get transaction history for a hall."""
    return HostelTransactionHistory.objects.filter(
        hostel__hall_id=hall_id
    ).order_by('-timestamp')


def list_transactions_by_change_type(hall_id, change_type):
    """Get transactions by change type."""
    return HostelTransactionHistory.objects.filter(
        hostel__hall_id=hall_id,
        change_type=change_type
    ).order_by('-timestamp')


# ══════════════════════════════════════════════════════════════
# WORKER REPORT QUERIES
# ══════════════════════════════════════════════════════════════

def get_worker_report(report_id):
    """Get a specific worker report."""
    return WorkerReport.objects.filter(id=report_id).first()

@transaction.atomic
def delete_worker_report(report_id):
    report = WorkerReport.objects.filter(id=report_id).first()
    if report:
        report.delete()
        return True
    return False


# ══════════════════════════════════════════════════════════════
# HM-WF-105: FINE MANAGEMENT QUERIES
# ══════════════════════════════════════════════════════════════

def list_student_fines(user):
    """List all fines for a specific student."""
    student = get_student(user)
    if not student:
        return HostelFine.objects.none()
    return HostelFine.objects.filter(student=student).prefetch_related('extra_details')


def list_hostel_fines(hall_ids=None):
    """List fines for specific hostels or all if none provided."""
    queryset = HostelFine.objects.all().select_related('student__user', 'hostel', 'imposed_by')
    if hall_ids is not None:
        queryset = queryset.filter(hostel__hall_id__in=hall_ids)
    return queryset.prefetch_related('extra_details')


def get_fine_by_id(fine_id):
    """Get a single fine by ID with details."""
    return HostelFine.objects.filter(id=fine_id).prefetch_related('extra_details').first()


def list_repeat_offenders(hall_ids=None, threshold=3):
    """
    Find students with unpaid fine counts exceeding threshold.
    Returns list of dictionaries with student info and fine metrics.
    """
    queryset = Student.objects.filter(fines__status=FineStatusChoices.PENDING)
    
    if hall_ids is not None:
        queryset = queryset.filter(fines__hostel__hall_id__in=hall_ids)
    
    return queryset.annotate(
        unpaid_count=Count('fines', filter=Q(fines__status=FineStatusChoices.PENDING)),
        total_unpaid_amount=Sum('fines__amount', filter=Q(fines__status=FineStatusChoices.PENDING))
    ).filter(unpaid_count__gte=threshold).order_by('-unpaid_count')


def get_fine_report_data(hall_ids=None):
    """Generate summary data for fine reports."""
    fines = list_hostel_fines(hall_ids=hall_ids)
    
    # Summary stats
    summary = {
        'total_fines': fines.count(),
        'total_amount': float(fines.aggregate(Sum('amount'))['amount__sum'] or 0),
        'unpaid_fines': fines.filter(status=FineStatusChoices.PENDING).count(),
        'unpaid_amount': float(fines.filter(status=FineStatusChoices.PENDING).aggregate(Sum('amount'))['amount__sum'] or 0),
        'resolved_today': fines.filter(paid_date__date=timezone.now().date()).count()
    }
    
    # Category breakdown
    categories = list(fines.values('category').annotate(
        count=Count('id'), 
        total=Sum('amount')
    ).order_by('-count'))
    
    # Trends (Last 6 months)
    six_months_ago = timezone.now() - timedelta(days=180)
    # Using TruncMonth for DB-agnostic grouping
    trends = list(fines.filter(imposed_date__gte=six_months_ago)
        .annotate(month=TruncMonth('imposed_date'))
        .values('month')
        .annotate(total_amount=Sum('amount'))
        .order_by('month'))
    
    # Format months for readability
    for trend in trends:
        if trend['month']:
            trend['month'] = trend['month'].strftime('%Y-%m')
            
    return {
        'summary': summary,
        'categories': categories,
        'trends': trends
    }


def list_staff_reports(staff_id):
    """Get all reports for a staff member."""
    return WorkerReport.objects.filter(
        worker_id=staff_id
    ).order_by('-year', '-month')


def list_hall_reports(hall_id):
    """Get all reports for a hall."""
    return WorkerReport.objects.filter(
        hall__hall_id=hall_id
    ).order_by('-year', '-month')


def get_monthly_report(staff_id, year, month):
    """Get report for a specific staff member for a specific month."""
    return WorkerReport.objects.filter(
        worker_id=staff_id,
        year=year,
        month=month
    ).first()


# ══════════════════════════════════════════════════════════════
# MISSING SELECTORS REQUIRED BY VIEWS
# ══════════════════════════════════════════════════════════════

def get_all_leaves():
    """Get all leaves with optimized queries (for staff views)."""
    return LeaveRequest.objects.select_related(
        'student__id__user',
        'decided_by'
    ).all().order_by('-created_at')


def get_student_leaves(user):
    """Get all leaves for a student user."""
    student = get_student(user)
    if not student:
        return LeaveRequest.objects.none()
    return LeaveRequest.objects.filter(
        student=student
    ).select_related(
        'student__id__user',
        'decided_by'
    ).order_by('-created_at')


def get_all_complaints():
    """Get all complaints with optimized queries (for staff views)."""
    return HostelComplaint.objects.select_related(
        'student',
        'hostel',
        'assigned_to_user'
    ).all().order_by('-created_at')


def get_student_complaints(user):
    """Get all complaints for a student user."""
    student = get_student(user.id)
    if not student:
        return HostelComplaint.objects.none()
    return HostelComplaint.objects.filter(
        student_id=student.pk
    ).select_related(
        'student__id__user',
        'assigned_to__id__user'
    ).order_by('-created_at')


def list_student_fines(user, status=None):
    """List all fines for a specific student."""
    student = get_student(user.id)
    if not student:
        return HostelFine.objects.none()
    queryset = HostelFine.objects.filter(student=student).select_related(
        'student__id__user', 
        'hostel', 
        'imposed_by'
    ).prefetch_related('extra_details').order_by('-imposed_date')
    
    if status:
        queryset = queryset.filter(status=status)
    return queryset


def list_hostel_fines(hall_ids=None, status=None):
    """List fines for specific hostels or all if none provided."""
    queryset = HostelFine.objects.all().select_related(
        'student__id__user', 
        'hostel', 
        'imposed_by'
    ).prefetch_related('extra_details').order_by('-imposed_date')
    
    if hall_ids is not None:
        queryset = queryset.filter(hostel__hall_id__in=hall_ids)
    
    if status:
        queryset = queryset.filter(status=status)
    return queryset


def get_fine_by_id(fine_id):
    """Get a single fine by ID with details."""
    return HostelFine.objects.filter(id=fine_id).select_related(
        'student__id__user', 
        'hostel', 
        'imposed_by'
    ).prefetch_related('extra_details').first()


def list_repeat_offenders(hall_ids=None, threshold=3):
    """Find students with multiple unpaid fines."""
    queryset = Student.objects.filter(fines__status=FineStatusChoices.PENDING)
    
    if hall_ids is not None:
        queryset = queryset.filter(fines__hostel__hall_id__in=hall_ids)
    
    offenders = queryset.annotate(
        unpaid_count=Count('fines', filter=Q(fines__status=FineStatusChoices.PENDING)),
        total_unpaid_amount=Sum('fines__amount', filter=Q(fines__status=FineStatusChoices.PENDING))
    ).filter(unpaid_count__gte=threshold).order_by('-unpaid_count').select_related('id__user')
    
    return offenders


def get_fine_report_data(hall_ids=None):
    """Generate summary data for fine reports."""
    fines = list_hostel_fines(hall_ids=hall_ids)
    
    # Summary stats
    summary = {
        'total_fines': fines.count(),
        'total_amount': float(fines.aggregate(Sum('amount'))['amount__sum'] or 0),
        'unpaid_fines': fines.filter(status=FineStatusChoices.PENDING).count(),
        'unpaid_amount': float(fines.filter(status=FineStatusChoices.PENDING).aggregate(Sum('amount'))['amount__sum'] or 0),
        'resolved_today': fines.filter(paid_date__date=timezone.now().date()).count()
    }
    
    # Category breakdown
    categories = list(fines.values('category').annotate(
        count=Count('id'), 
        total=Sum('amount')
    ).order_by('-count'))
    
    # Trends (Last 6 months)
    six_months_ago = timezone.now() - timedelta(days=180)
    # Using TruncMonth for DB-agnostic grouping
    trends = list(fines.filter(imposed_date__gte=six_months_ago)
        .annotate(month=TruncMonth('imposed_date'))
        .values('month')
        .annotate(total_amount=Sum('amount'))
        .order_by('month'))
    
    # Format months for readability
    for trend in trends:
        if trend['month']:
            trend['month'] = trend['month'].strftime('%Y-%m')
            
    return {
        'summary': summary,
        'categories': categories,
        'trends': trends
    }


def get_all_schedules():
    """Get all staff schedules with optimized queries."""
    return StaffSchedule.objects.select_related(
        'hostel',
        'staff__id__user'
    ).all().order_by('day_of_week', 'start_time')


def get_all_inventory():
    """Get all inventory items with optimized queries."""
    return HostelInventory.objects.select_related(
        'hostel'
    ).all().order_by('hostel', 'item_name')

# ══════════════════════════════════════════════════════════════
# NEW FEATURE QUERIES (Room Vacation & Extended Stay)
# ══════════════════════════════════════════════════════════════

from .models import RoomVacationRequest, ExtendedStayApplication

def list_room_vacations(filters=None):
    queryset = RoomVacationRequest.objects.select_related('student', 'student__id__user', 'room', 'hall')
    if filters:
        if 'student' in filters:
            queryset = queryset.filter(student=filters['student'])
        if 'hall_id' in filters:
            queryset = queryset.filter(hall_id=filters['hall_id'])
    return queryset.order_by('-created_at')

def get_room_vacation(pk):
    return RoomVacationRequest.objects.filter(pk=pk).first()

def list_extended_stays(filters=None):
    queryset = ExtendedStayApplication.objects.select_related('student', 'student__id__user', 'room', 'hall')
    if filters:
        if 'student' in filters:
            queryset = queryset.filter(student=filters['student'])
        if 'hall_id' in filters:
            queryset = queryset.filter(hall_id=filters['hall_id'])
    return queryset.order_by('-created_at')

def list_all_application_windows():
    """List all accommodation application windows, ordered by end date."""
    from .models import AccommodationApplicationWindow
    return AccommodationApplicationWindow.objects.all().order_by('-end_date')


def get_extended_stay(pk):
    """Retrieve a specific extended stay application by its primary key."""
    from .models import ExtendedStayApplication
    return ExtendedStayApplication.objects.filter(pk=pk).first()


# ══════════════════════════════════════════════════════════════
# MODERN INVENTORY SELECTORS
# ══════════════════════════════════════════════════════════════

def list_inventory_items(user):
    """
    List inventory items scoped to user role.
    - super_admin: all items
    - warden/caretaker: items in assigned hostels
    """
    queryset = InventoryItem.objects.select_related('hostel').all()
    
    if user.is_superuser:
        return queryset
        
    assigned_hostel_ids = list_assigned_hostels(user).values_list('hall_id', flat=True)
    return queryset.filter(hostel_id__in=assigned_hostel_ids)


def get_inventory_item(id, user=None):
    """Fetch an inventory item, optionally checking user scope."""
    item = InventoryItem.objects.filter(id=id).select_related('hostel').first()
    if not item or user is None or user.is_superuser:
        return item
        
    assigned_hostel_ids = list_assigned_hostels(user).values_list('hall_id', flat=True)
    if item.hostel_id not in assigned_hostel_ids:
        return None
    return item


def list_discrepancies(user):
    """List discrepancies scoped to user role."""
    queryset = InventoryDiscrepancy.objects.select_related('item', 'hostel', 'reported_by').all()
    
    if user.is_superuser:
        return queryset
        
    assigned_hostel_ids = list_assigned_hostels(user).values_list('hall_id', flat=True)
    return queryset.filter(hostel_id__in=assigned_hostel_ids)


def list_resource_requests(user):
    """
    List resource requests scoped to user role.
    - super_admin: all requests
    - warden/caretaker: requests from assigned hostels
    """
    queryset = ResourceRequest.objects.select_related('hostel', 'requested_by', 'reviewed_by').all()
    
    if user.is_superuser:
        return queryset
        
    assigned_hostel_ids = list_assigned_hostels(user).values_list('hall_id', flat=True)
    return queryset.filter(hostel_id__in=assigned_hostel_ids)


def list_inventory_audit_logs(user, item_id=None):
    """List audit logs scoped to user role."""
    queryset = InventoryAuditLog.objects.select_related('item', 'hostel', 'performed_by').all()
    
    if item_id:
        queryset = queryset.filter(item_id=item_id)
        
    if user.is_superuser:
        return queryset
        
    assigned_hostel_ids = list_assigned_hostels(user).values_list('hall_id', flat=True)
    return queryset.filter(hostel_id__in=assigned_hostel_ids)


# ══════════════════════════════════════════════════════════════
# HM-WF-110: NOTICE BOARD SELECTORS
# ══════════════════════════════════════════════════════════════

def get_notice(notice_id):
    """Retrieve a specific notice by ID."""
    return Notice.objects.filter(id=notice_id).select_related('hostel', 'created_by').first()


def list_active_notices_for_student(user):
    """
    List active/published notices for a student.
    Matches: (hostel=None OR hostel=student_hostel) AND status=PUBLISHED.
    """
    student = get_student(user)
    if not student:
        return Notice.objects.none()

    # Get active allotment to determine student's hostel
    allotment = get_active_allotment_by_student(student)
    hostel_id = allotment.hostel_id if allotment else None

    now = timezone.now().date()
    
    queryset = Notice.objects.filter(
        status=NoticeStatus.PUBLISHED,
        start_date__lte=now,
        end_date__gte=now
    ).filter(
        models.Q(hostel__isnull=True) | models.Q(hostel_id=hostel_id)
    ).select_related('hostel', 'created_by')

    return queryset.order_by('-priority', '-created_at')


def list_notices_for_staff(user):
    """
    List notices for staff (Warden/Caretaker).
    Scoped to hostels they are assigned to manage.
    """
    if user.is_superuser:
        return Notice.objects.all().select_related('hostel', 'created_by')
        
    assigned_hostel_ids = list_assigned_hostels(user).values_list('hall_id', flat=True)
    return Notice.objects.filter(
        models.Q(hostel_id__in=assigned_hostel_ids) | models.Q(hostel__isnull=True)
    ).select_related('hostel', 'created_by').order_by('-created_at')


def list_notice_history(user):
    """
    List archived or expired notices.
    """
    now = timezone.now().date()
    queryset = Notice.objects.filter(
        models.Q(status=NoticeStatus.ARCHIVED) | models.Q(end_date__lt=now)
    )

    if user.is_superuser or user.is_staff or is_user_warden_or_caretaker(user):
        if not user.is_superuser:
            assigned_hostel_ids = list_assigned_hostels(user).values_list('hall_id', flat=True)
            queryset = queryset.filter(hostel_id__in=assigned_hostel_ids)
    else:
        student = get_student(user)
        allotment = get_active_allotment_by_student(student)
        hostel_id = allotment.hostel_id if allotment else None
        queryset = queryset.filter(
            models.Q(hostel__isnull=True) | models.Q(hostel_id=hostel_id)
        )

    return queryset.select_related('hostel', 'created_by').order_by('-end_date')


def get_notice_read_status(notice_id, user):
    """Check if a specific user has read a notice."""
    student = get_student(user)
    if not student:
        return False
    return NoticeReadStatus.objects.filter(notice_id=notice_id, student=student).exists()


def get_notice_read_count(notice_id):
    """Get total number of students who read a notice."""
    return NoticeReadStatus.objects.filter(notice_id=notice_id).count()


# ══════════════════════════════════════════════════════════════
# SECURITY MANAGEMENT SELECTORS
# ══════════════════════════════════════════════════════════════

def list_security_guards(hostel_ids=None):
    """
    List security guards. 
    Warden/Caretaker only sees guards for their assigned hostels.
    """
    queryset = SecurityGuard.objects.all()
    if hostel_ids:
        queryset = queryset.filter(hostel_id__in=hostel_ids)
    return queryset.order_by('name')


def list_guard_shifts(hostel_id=None, date=None):
    """List guard shifts, optionally filtered by hostel and date."""
    queryset = GuardShift.objects.all().select_related('guard', 'hostel', 'assigned_by')
    if hostel_id:
        queryset = queryset.filter(hostel_id=hostel_id)
    if date:
        queryset = queryset.filter(date=date)
    return queryset.order_by('date', 'start_time')


def get_guard_conflict(guard_id, date, start_time, end_time, exclude_shift_id=None):
    """Check for overlapping shifts for a guard (BR-HM-016.a)."""
    queryset = GuardShift.objects.filter(
        guard_id=guard_id,
        date=date,
        start_time__lt=end_time,
        end_time__gt=start_time
    )
    if exclude_shift_id:
        queryset = queryset.exclude(id=exclude_shift_id)
    return queryset.first()




def list_shift_audit_logs(hostel_id=None):
    """List immutable shift audit logs scoped by hostel."""
    queryset = ShiftScheduleLog.objects.all().select_related('hostel', 'guard', 'performed_by')
    if hostel_id:
        queryset = queryset.filter(hostel_id=hostel_id)
    return queryset.order_by('-timestamp')

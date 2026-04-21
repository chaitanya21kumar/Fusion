"""
Hostel Management Services

This module contains ALL business logic, state mutations, and rule enforcement.
- Business Rules are enforced here and raise custom exceptions on violation
- All database mutations go through services
- Services use selectors for queries
"""

from django.utils import timezone
from datetime import timedelta
from decimal import Decimal

from .models import (
    LeaveRequest, StudentAttendanceRecord, AttendanceStatus,
    HostelComplaint, RoomAllocationChange,
    HostelFine, GuestRoomBooking, GuestRoom, Hostel,
    Room, RoomAllotment, HostelStaffAssignment, HostelAuditLog, AccommodationApplicationWindow,
    AccommodationRequest, StaffRoleChoices,
    RoomSetupStatusChoices, ComplaintHistory,
    ComplaintCategoryChoices, ComplaintStatusChoices,
    LeaveStatusChoices, FineStatusChoices, BookingStatusChoices,
    AllocationChangeStatusChoices, FineCategoryChoices, FineExtraDetail,
    Notice, NoticeReadStatus, NoticeStatus,
    NoticePriority, SecurityGuard, GuardShift, ShiftScheduleLog,
    ShiftActionChoices
)
from notifications.signals import notify
from django.db import transaction
from applications.globals.models import Faculty, Staff
from . import selectors


# ══════════════════════════════════════════════════════════════
# CUSTOM EXCEPTIONS
# ══════════════════════════════════════════════════════════════

class HostelManagementException(Exception):
    """Base exception for hostel management errors."""


class LeaveEligibilityError(HostelManagementException):
    """Raised when leave eligibility is not met (BR-HM-101)."""


class LeaveDateError(HostelManagementException):
    """Raised when leave dates are invalid (BR-HM-102)."""


class LeaveJustificationError(HostelManagementException):
    """Raised when leave lacks justification (BR-HM-103)."""


class LeaveAuthorityError(HostelManagementException):
    """Raised when leave decision maker lacks authority (BR-HM-104)."""


class FineValidationError(HostelManagementException):
    """Raised when fine parameters violate business rules (BR-HM-013)."""


class ComplaintEligibilityError(HostelManagementException):
    """Raised when complaint eligibility is not met (BR-HM-106)."""


class ComplaintRoutingError(HostelManagementException):
    """Raised when complaint routing fails (BR-HM-107)."""


class ResolutionRemarksError(HostelManagementException):
    """Raised when resolution remarks are missing (BR-HM-108)."""


class EscalationAuthorizationError(HostelManagementException):
    """Raised when escalation is not authorized (BR-HM-109)."""


class WardenAuthorityError(HostelManagementException):
    """Raised when warden authority is required (BR-HM-110)."""


class ApplicationWindowError(HostelManagementException):
    """Raised when application window is closed (BR-HM-111)."""


class AllotmentCapacityError(HostelManagementException):
    """Raised when room capacity would be exceeded (BR-HM-112)."""


class RoomChangeEligibilityError(HostelManagementException):
    """Raised when student is not eligible for room change (BR-HM-115)."""


class DualApprovalError(HostelManagementException):
    """Raised when dual approval requirement is not met (BR-HM-116)."""


class OccupancyReconciliationError(HostelManagementException):
    """Raised when occupancy reconciliation fails (BR-HM-117)."""


class RoomVacationPrerequisiteError(HostelManagementException):
    """Raised when room vacation prerequisites are not met (BR-015)."""


class FineValidationError(HostelManagementException):
    """Raised when fine validation fails (BR-HM-013)."""


# ══════════════════════════════════════════════════════════════
# HM-WF-112: GUEST ROOM EXCEPTIONS (CHUNK 12)
# ══════════════════════════════════════════════════════════════

class GuestRoomBookingError(HostelManagementException):
    """Base exception for guest room booking errors."""

class GuestRoomAvailabilityError(GuestRoomBookingError):
    """Raised when room is not available for requested dates."""

class GuestRoomPolicyError(GuestRoomBookingError):
    """Raised when booking violates hostel policies."""

class GuestRoomInspectionError(GuestRoomBookingError):
    """Raised during check-out if inspection fails."""


class GuardShiftConflictError(HostelManagementException):
    """Raised when shift timing overlaps with existing shifts (BR-HM-016.a)."""


class GuardPolicyError(HostelManagementException):
    """Raised when safety policies (rest periods, etc.) are violated."""


# ══════════════════════════════════════════════════════════════
# HM-WF-101: LEAVE MANAGEMENT SERVICES
# ══════════════════════════════════════════════════════════════

def create_leave_request(student, start_date, end_date, reason, documents=None):
    """
    Create a new leave request.
    
    Enforces:
    - BR-HM-101: Leave Eligibility Based on Hostel Residency
    - BR-HM-102: Leave Date Boundary Validation
    - BR-HM-103: Mandatory Leave Justification & Documents
    """
    # BR-HM-101: Check if student is currently in hostel
    current_allotment = selectors.get_active_allotment_by_student(student)
    if not current_allotment:
        raise LeaveEligibilityError(
            "Student must have an active hostel allotment to request leave."
        )
    
    # BR-HM-102: Validate leave dates
    today = timezone.now().date()
    if start_date < today:
        raise LeaveDateError("Leave start date cannot be in the past.")
    if end_date < start_date:
        raise LeaveDateError("Leave end date must be after start date.")
    
    # Check for maximum leave duration (e.g., 90 days)
    leave_duration = (end_date - start_date).days
    if leave_duration > 90:
        raise LeaveDateError("Leave duration cannot exceed 90 days.")
    
    # BR-HM-103: Check for mandatory justification & documents
    if not reason or len(reason.strip()) < 10:
        raise LeaveJustificationError(
            "Leave must have a valid reason (at least 10 characters)."
        )
    
    if not documents:
        raise LeaveJustificationError(
            "Supporting documents are strictly mandatory for all leave requests."
        )
    
    # Create the leave request
    leave = LeaveRequest.objects.create(
        student=student,
        hostel=current_allotment.hostel,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        documents=documents,
        status=LeaveStatusChoices.PENDING
    )
    
    # Notify Caretaker
    try:
        caretaker = selectors.get_hostel_caretaker(current_allotment.hostel.hall_id)
        if caretaker:
            notify.send(
                sender=student.id.user,
                recipient=caretaker.user,
                verb="submitted a leave request",
                action_object=leave,
                description=f"Student {student} has requested leave from {start_date} to {end_date}.",
                data={"module": "Hostel Management", "url": "hostel-management/leave/"}
            )
    except Exception as e:
        print(f"DEBUG: Notification failed: {e}")

    return leave


def approve_leave(leave_id, decided_by, remarks=None):
    """
    Approve a leave request.
    
    Enforces:
    - BR-HM-104: Leave Decision Authority Enforcement
    - BR-HM-105: Attendance Synchronization on Leave Approval
    """
    leave = selectors.get_student_leave(leave_id)
    if not leave:
        raise HostelManagementException(f"Leave Request {leave_id} not found.")
    
    if leave.status != LeaveStatusChoices.PENDING:
        raise HostelManagementException(
            f"Cannot approve leave in {leave.status} status."
        )
    
    # BR-HM-104: Authority check (caretaker/warden must process)
    if not decided_by:
        raise LeaveAuthorityError("Leave approval requires authorized personnel.")
    
    with transaction.atomic():
        leave.status = LeaveStatusChoices.APPROVED
        leave.decided_by = decided_by
        leave.decision_remarks = remarks
        leave.updated_at = timezone.now()
        leave.save()
        
        # BR-HM-105: Mark student as OnLeave for leave dates
        _mark_leave_attendance(leave)
    
    # Send Notification
    notify.send(
        sender=decided_by,
        recipient=leave.student.id.user,
        verb="approved your leave request",
        action_object=leave,
        description=f"Your leave from {leave.start_date} to {leave.end_date} has been approved.",
        data={"module": "Hostel Management", "url": "hostel-management/leave/"}
    )
    
    return leave


def reject_leave(leave_id, decided_by, rejection_reason):
    """Reject a leave request."""
    leave = selectors.get_student_leave(leave_id)
    if not leave:
        raise HostelManagementException(f"Leave Request {leave_id} not found.")
    
    if leave.status != LeaveStatusChoices.PENDING:
        raise HostelManagementException(
            f"Cannot reject leave in {leave.status} status."
        )
    
    if not rejection_reason or len(rejection_reason.strip()) < 5:
        raise HostelManagementException("Rejection remarks are mandatory and must be at least 5 characters.")
    
    leave.status = LeaveStatusChoices.REJECTED
    leave.decided_by = decided_by
    leave.decision_remarks = rejection_reason
    leave.updated_at = timezone.now()
    leave.save()
    
    # Send Notification
    notify.send(
        sender=decided_by,
        recipient=leave.student.id.user,
        verb="rejected your leave request",
        action_object=leave,
        description=f"Your leave from {leave.start_date} to {leave.end_date} has been rejected. Reason: {rejection_reason}",
        data={"module": "Hostel Management", "url": "hostel-management/leave/"}
    )
    
    return leave


def cancel_leave(leave_id):
    """Cancel an approved leave request."""
    leave = selectors.get_student_leave(leave_id)
    if not leave:
        raise HostelManagementException(f"Leave {leave_id} not found.")
    
    if leave.status != LeaveStatusChoices.APPROVED:
        raise HostelManagementException(
            f"Only approved leaves can be cancelled. Current status: {leave.status}"
        )
    
    leave.status = LeaveStatusChoices.CANCELLED
    leave.updated_at = timezone.now()
    leave.save()
    
    # Notify Staff who approved (if applicable)
    if leave.decided_by:
        try:
            notify.send(
                sender=leave.student.id.user,
                recipient=leave.decided_by,
                verb="cancelled their approved leave",
                action_object=leave,
                description=f"Student {leave.student} cancelled their approved leave ({leave.start_date} to {leave.end_date}).",
                data={"module": "Hostel Management", "url": "hostel-management/leave/"}
            )
        except Exception as e:
            print(f"DEBUG: Notification failed: {e}")

    return leave


def _mark_leave_attendance(leave):
    """Mark attendance for leave dates (Internal only)."""
    current_date = leave.start_date
    
    while current_date <= leave.end_date:
        StudentAttendanceRecord.objects.update_or_create(
            student=leave.student,
            date=current_date,
            defaults={
                'status': AttendanceStatus.ON_LEAVE,
                'leave_request': leave
            }
        )
        current_date += timedelta(days=1)


def mark_attendance_bulk(date, attendance_data):
    """
    Bulk mark attendance for students.
    attendance_data: list of dicts [{'student_id': id, 'status': status, 'remarks': str}]
    """
    from applications.academic_information.models import Student
    records = []
    with transaction.atomic():
        for entry in attendance_data:
            student = Student.objects.get(pk=entry['student_id'])
            record, created = StudentAttendanceRecord.objects.update_or_create(
                student=student,
                date=date,
                defaults={
                    'status': entry['status'],
                }
            )
            records.append(record)
    return records


def process_attendance_excel(hall_id, date, excel_file):
    """
    Process attendance from an Excel file for a specific date and hostel.
    Expected Format: Col A: Roll Number, Col B: Status (Present/Absent).
    """
    import openpyxl
    from applications.academic_information.models import Student
    from .models import AttendanceStatus

    # Get roll numbers of students currently allotted to this hostel
    valid_roll_numbers = set(Student.objects.filter(
        room_allotments__hostel__hall_id=hall_id,
        room_allotments__is_active=True
    ).values_list('id__id', flat=True))

    wb = openpyxl.load_workbook(excel_file)
    sheet = wb.active
    
    records = []
    errors = []
    
    with transaction.atomic():
        for row_idx, row in enumerate(sheet.iter_rows(min_row=2, values_only=True), start=2):
            if not row or len(row) < 2:
                continue
                
            roll_no, status_str = row[0], row[1]
            if roll_no is None:
                continue
                
            # Handle cases where openpyxl might read number as float (e.g. 2021001.0)
            if isinstance(roll_no, float):
                roll_no = int(roll_no)
            
            roll_no = str(roll_no).strip()
            if roll_no not in valid_roll_numbers:
                errors.append(f"Row {row_idx}: Student {roll_no} not allotted to this hostel.")
                continue
            
            status_str = str(status_str).strip().lower()
            if status_str in ['p', 'present']:
                status = AttendanceStatus.PRESENT
            elif status_str in ['a', 'absent']:
                status = AttendanceStatus.ABSENT
            else:
                errors.append(f"Row {row_idx}: Invalid status '{status_str}' for {roll_no}.")
                continue
            
            student = Student.objects.get(id__id=roll_no)
            record, created = StudentAttendanceRecord.objects.update_or_create(
                student=student,
                date=date,
                defaults={'status': status}
            )
            records.append(record)
            
    return {
        'records_count': len(records),
        'errors': errors
    }


# ══════════════════════════════════════════════════════════════
# HM-WF-102: COMPLAINT MANAGEMENT SERVICES
# ══════════════════════════════════════════════════════════════

def _generate_complaint_uid():
    """Generates a human-readable unique complaint ID: COMP-YYYYMMDD-XXXX."""
    date_str = timezone.now().strftime('%Y%m%d')
    with transaction.atomic():
        # Get count of complaints created today for sequence
        today_count = HostelComplaint.objects.filter(created_at__date=timezone.now().date()).count() + 1
        return f"COMP-{date_str}-{str(today_count).zfill(4)}"

def _log_complaint_history(complaint, changed_by, old_status, new_status, remarks=""):
    """Internal helper to log status changes."""
    ComplaintHistory.objects.create(
        complaint=complaint,
        changed_by=changed_by,
        old_status=old_status,
        new_status=new_status,
        remarks=remarks
    )

def create_complaint(student, category, description, attachments=None):
    """
    Submit a new complaint with auto-routing logic.
    - BR-HM-106: Active Allotment Prerequisite
    - BR-HM-107: Auto-routing by Category
    """
    # BR-HM-106: Block if student has no active room allotment
    active_allotment = selectors.get_active_allotment_by_student(student)
    if not active_allotment:
        raise ComplaintEligibilityError("Active hostel allotment required to submit complaints.")

    # BR-HM-107: Auto-routing
    hostel = active_allotment.hostel
    assigned_to_user = None
    
    if category == ComplaintCategoryChoices.SECURITY:
        # Route to Warden
        warden_asgn = selectors.get_hostel_warden(hostel.hall_id)
        if warden_asgn:
            assigned_to_user = warden_asgn.user
    else:
        # Route to Caretaker
        caretaker_asgn = selectors.get_hostel_caretaker(hostel.hall_id)
        if caretaker_asgn:
            assigned_to_user = caretaker_asgn.user

    with transaction.atomic():
        complaint = HostelComplaint.objects.create(
            student=student,
            hostel=hostel,
            category=category,
            description=description,
            attachments=attachments,
            status=ComplaintStatusChoices.SUBMITTED,
            assigned_to_user=assigned_to_user,
            complaint_uid=_generate_complaint_uid()
        )
        
        _log_complaint_history(
            complaint=complaint,
            changed_by=student.id.user,
            old_status=None,
            new_status=ComplaintStatusChoices.SUBMITTED,
            remarks="Complaint created and auto-routed."
        )

    # Notify assignee
    if assigned_to_user:
        notify.send(
            sender=student.id.user,
            recipient=assigned_to_user,
            verb="new complaint assigned",
            action_object=complaint,
            description=f"New {category} complaint {complaint.complaint_uid} submitted by {student}.",
            data={"module": "Hostel Management", "url": "hostel-management/complaints/"}
        )

    return complaint


def update_complaint_to_in_progress(complaint_id, staff_user, remarks=""):
    """Mark complaint as InProgress when staff starts working on it."""
    complaint = selectors.get_complaint(complaint_id)
    if not complaint:
        raise HostelManagementException("Complaint not found.")
    
    old_status = complaint.status
    if old_status != ComplaintStatusChoices.SUBMITTED:
        raise HostelManagementException("Can only move 'Submitted' complaints to 'In Progress'.")

    with transaction.atomic():
        complaint.status = ComplaintStatusChoices.IN_PROGRESS
        complaint.save()
        _log_complaint_history(complaint, staff_user, old_status, ComplaintStatusChoices.IN_PROGRESS, remarks)
    
    # Notify student
    try:
        notify.send(
            sender=staff_user,
            recipient=complaint.student.id.user,
            verb="started processing your complaint",
            action_object=complaint,
            description=f"Your complaint {complaint.complaint_uid} ({complaint.category}) is now being processed.",
            data={"module": "Hostel Management", "url": "hostel-management/complaints/"}
        )
    except Exception as e:
        print(f"DEBUG: Notification failed: {e}")

    return complaint

def escalate_complaint(complaint_id, staff_user, reason):
    """
    Escalate complaint to Warden.
    - BR-HM-109: Only InProgress complaints can be escalated
    """
    complaint = selectors.get_complaint(complaint_id)
    if not complaint:
        raise HostelManagementException("Complaint not found.")
    
    # BR-HM-111: Wardens cannot escalate further
    if selectors.is_user_warden(staff_user):
        raise WardenAuthorityError("Wardens cannot escalate complaints further. They are the final authority for resolution.")
    
    # BR-HM-109: Block if status is not InProgress
    if complaint.status != ComplaintStatusChoices.IN_PROGRESS:
        raise EscalationAuthorizationError("Only complaints 'In Progress' can be escalated.")

    # Find Warden
    warden_asgn = selectors.get_hostel_warden(complaint.hostel.hall_id)
    if not warden_asgn:
        raise WardenAuthorityError("No active Warden found for this hostel.")

    old_status = complaint.status
    with transaction.atomic():
        complaint.status = ComplaintStatusChoices.ESCALATED
        complaint.assigned_to_user = warden_asgn.user
        complaint.save()
        _log_complaint_history(complaint, staff_user, old_status, ComplaintStatusChoices.ESCALATED, reason)

    notify.send(
        sender=staff_user,
        recipient=warden_asgn.user,
        verb="complaint escalated",
        action_object=complaint,
        description=f"Complaint {complaint.complaint_uid} escalated by {staff_user.get_full_name()}.",
        data={"module": "Hostel Management", "url": "hostel-management/complaints/"}
    )
    
    return complaint

def resolve_complaint(complaint_id, resolver_user, resolution_remarks):
    """
    Resolve a complaint.
    - BR-HM-108: Remarks mandatory
    - BR-HM-110: Only Warden resolve if Escalated
    """
    complaint = selectors.get_complaint(complaint_id)
    if not complaint:
        raise HostelManagementException("Complaint not found.")

    if complaint.status in [ComplaintStatusChoices.RESOLVED, ComplaintStatusChoices.CLOSED]:
        raise HostelManagementException(f"Cannot resolve a complaint that is already {complaint.status.lower()}.")

    # BR-HM-108: Resolve remarks mandatory
    if not resolution_remarks or len(resolution_remarks.strip()) < 10:
        raise ResolutionRemarksError("Resolution remarks are mandatory (min 10 chars).")

    # BR-HM-110: Role-based authority separation
    is_warden = selectors.is_user_warden(resolver_user)
    is_caretaker = selectors.is_user_caretaker(resolver_user)

    if is_warden:
        if complaint.status != ComplaintStatusChoices.ESCALATED:
            raise WardenAuthorityError("Wardens can only resolve complaints that have been escalated to them.")
    elif is_caretaker:
        if complaint.status != ComplaintStatusChoices.IN_PROGRESS:
            raise HostelManagementException("Caretakers can only resolve complaints that are currently 'In Progress'.")
    else:
        raise HostelManagementException("Only authorized staff or wardens can resolve complaints.")

    old_status = complaint.status
    with transaction.atomic():
        complaint.status = ComplaintStatusChoices.RESOLVED
        complaint.resolution_remarks = resolution_remarks
        complaint.resolved_at = timezone.now()
        complaint.save()
        _log_complaint_history(complaint, resolver_user, old_status, ComplaintStatusChoices.RESOLVED, resolution_remarks)

    # Notify student
    notify.send(
        sender=resolver_user,
        recipient=complaint.student.id.user,
        verb="complaint resolved",
        action_object=complaint,
        description=f"Your complaint {complaint.complaint_uid} has been resolved.",
        data={"module": "Hostel Management", "url": "hostel-management/complaints/"}
    )
    
    return complaint


# ══════════════════════════════════════════════════════════════
# HM-WF-103: ACCOMMODATION SERVICES
# ══════════════════════════════════════════════════════════════

def create_accommodation_request(student, window_id, preferred_hostel_type, preferred_room_type):
    """
    Submits a new accommodation request for a student.
    - BR-HM-111: Application Window Enforcement
    """
    window = AccommodationApplicationWindow.objects.filter(id=window_id).first()
    if not window or not window.is_open:
        raise ApplicationWindowError("The application window is currently closed.")

    # Check for existing request
    if selectors.get_student_accommodation_request(student, window):
        raise HostelManagementException("You have already submitted a request for this window.")

    request = AccommodationRequest.objects.create(
        student=student,
        window=window,
        preferred_hostel_type=preferred_hostel_type,
        preferred_room_type=preferred_room_type,
        status=AccommodationRequest.Status.PENDING
    )
    return request


def perform_bulk_allotment(request_ids, allotted_by):
    """
    Performs bulk allotment for selected requests.
    - BR-HM-112: Capacity Safeguard
    - BR-HM-113: Transaction Safety with select_for_update
    - BR-HM-114: Notification Trigger (Stub)
    """
    results = {
        'success': [],
        'failed': []
    }

    with transaction.atomic():
        # Lock requests and related student profiles
        requests = AccommodationRequest.objects.select_for_update().filter(
            id__in=request_ids,
            status=AccommodationRequest.Status.PENDING
        )

        for req in requests:
            try:
                # Find suitable room using selector
                # Criteria: matches preferred_hostel_type and preferred_room_type
                # AND current_occupancy < capacity
                suitable_rooms = Room.objects.select_for_update().filter(
                    hostel__type=req.preferred_hostel_type,
                    capacity__gt=F('current_occupancy'),
                    hostel__status='Active' # Depend on Chunk 1 Hostel status
                ).order_by('floor', 'room_number')

                # For simplicity, we filter room type by capacity (Single=1, Double=2, etc. - usually defined in business rules)
                # Here we assume room_type maps to capacity for filter
                # Single=1, Double=2, Triple=3
                capacity_map = {'Single': 1, 'Double': 2, 'Triple': 3}
                preferred_capacity = capacity_map.get(req.preferred_room_type, 1)
                
                room = suitable_rooms.filter(capacity=preferred_capacity).first()

                if not room:
                    results['failed'].append({
                        'request_id': req.id,
                        'reason': 'No suitable rooms available for preferred types.'
                    })
                    continue

                # Create Allotment
                allotment = RoomAllotment.objects.create(
                    student=req.student,
                    room=room,
                    hostel=room.hostel,
                    allotted_by=allotted_by,
                    is_active=True
                )

                # Update Room occupancy
                room.current_occupancy += 1
                room.save()

                # BR-HM-036: Transfer unpaid fines to the new hostel
                transfer_student_fines(req.student, room.hostel)

                # Update Request status
                req.status = AccommodationRequest.Status.ALLOTTED
                req.save()

                results['success'].append({
                    'request_id': req.id,
                    'room_number': room.room_number,
                    'hostel_name': room.hostel.name
                })

                # BR-HM-114: Trigger Notification
                _trigger_allotment_notification(allotment)

            except Exception as e:
                results['failed'].append({
                    'request_id': req.id,
                    'reason': str(e)
                })

    return results


def _trigger_allotment_notification(allotment):
    """Implementation of BR-HM-114: Mandatory Allotment Notification."""
    try:
        notify.send(
            sender=allotment.allotted_by,
            recipient=allotment.student.id.user,
            verb="allotted a room to you",
            action_object=allotment,
            description=f"You have been successfully allotted room {allotment.room.room_number} in {allotment.hostel.name}.",
            data={"module": "Hostel Management", "url": "hostel-management/room-allocation/"}
        )
    except Exception as e:
        print(f"DEBUG: Allotment notification failed: {e}")


# ══════════════════════════════════════════════════════════════
# HM-WF-104: ROOM CHANGE SERVICES
# ══════════════════════════════════════════════════════════════

def request_room_change(student, current_room, requested_room, reason):
    """
    Request a room change.
    
    Enforces:
    - BR-HM-115: Room Change Eligibility Rule
    """
    # BR-HM-115: Student must have current allocation
    current_allocation = selectors.get_active_allotment_by_student(student)
    if not current_allocation:
        raise RoomChangeEligibilityError(
            "Student must have an active hostel allocation to request room change."
        )

    
    # Check if currently allocated room matches
    if current_allocation.room != current_room:
        raise RoomChangeEligibilityError(
            "Requested current room does not match student's allocation."
        )
    
    # Cannot request change to same room
    if current_room == requested_room:
        raise RoomChangeEligibilityError(
            "Cannot request change to the same room."
        )
    
    # Validate reason
    if not reason or len(reason.strip()) < 10:
        raise RoomChangeEligibilityError(
            "Room change reason must be at least 10 characters."
        )
    
    change_request = RoomAllocationChange.objects.create(
        student=student,
        current_room=current_room,
        requested_room=requested_room,
        reason=reason,
        status=AllocationChangeStatusChoices.REQUESTED
    )
    
    # Notify Warden
    try:
        warden_asgn = selectors.get_hostel_warden(current_allocation.hostel.hall_id)
        if warden_asgn:
            notify.send(
                sender=student.id.user,
                recipient=warden_asgn.user,
                verb="requested a room change",
                action_object=change_request,
                description=f"Student {student} has requested a change from {current_room} to {requested_room}.",
                data={"module": "Hostel Management", "url": "hostel-management/room-allocation/changes/"}
            )
    except Exception as e:
        print(f"DEBUG: Room change request notification failed: {e}")

    return change_request


def approve_room_change_warden(change_id, warden, remarks=None):
    """
    Warden approves room change.
    
    Enforces:
    - BR-HM-116: Dual Approval Requirement
    """
    change = selectors.get_room_change(change_id)
    if not change:
        raise HostelManagementException(f"Room change {change_id} not found.")
    
    if change.status != AllocationChangeStatusChoices.REQUESTED:
        raise DualApprovalError(
            f"Room change is in {change.status} status and cannot be approved."
        )
    
    change.status = AllocationChangeStatusChoices.APPROVED_WARDEN
    change.approved_by_warden = warden
    change.warden_approval_date = timezone.now()
    change.warden_remarks = remarks
    change.save()
    
    # Notify Student
    try:
        notify.send(
            sender=warden.id.user,
            recipient=change.student.id.user,
            verb="provisionally approved your room change",
            action_object=change,
            description=f"Your room change request has been approved by the Warden. Final confirmation pending from Caretaker.",
            data={"module": "Hostel Management", "url": "hostel-management/room-allocation/changes/"}
        )
    except Exception as e:
        print(f"DEBUG: Warden approval notification failed: {e}")

    return change


def approve_room_change_caretaker(change_id, caretaker, remarks=None):
    """
    Caretaker approves room change (final approval).
    
    Enforces:
    - BR-HM-116: Dual Approval Requirement (completes dual approval)
    - BR-HM-117: Occupancy Reconciliation on Room Change
    """
    from .models import RoomAllotment
    
    change = selectors.get_room_change(change_id)
    if not change:
        raise HostelManagementException(f"Room change {change_id} not found.")
    
    if change.status != AllocationChangeStatusChoices.APPROVED_WARDEN:
        raise DualApprovalError(
            "Room change must be approved by warden before caretaker approval."
        )
    
    # BR-HM-117: Check capacity of requested room
    if change.requested_room.current_occupancy >= change.requested_room.capacity:
        raise AllotmentCapacityError(
            f"Requested room is at full capacity and cannot accommodate change."
        )
    
    with transaction.atomic():
        # Update allotments (new model 'RoomAllotment')
        current_allotment = selectors.get_active_allotment_by_student(change.student)
        if current_allotment:
            # Release from current room
            current_allotment.is_active = False
            current_allotment.vacated_at = timezone.now()
            current_allotment.save()
            
            # Update current room occupancy
            if current_allotment.room:
                current_allotment.room.current_occupancy = max(0, current_allotment.room.current_occupancy - 1)
                if current_allotment.room.current_occupancy < current_allotment.room.capacity:
                    current_allotment.room.status = 'Available'
                current_allotment.room.save()
        
        # Create new allotment in requested room
        RoomAllotment.objects.create(
            student=change.student,
            room=change.requested_room,
            hostel=change.requested_room.hostel,
            allotted_by=caretaker.id.user,
            is_active=True
        )
        
        # Update requested room occupancy
        change.requested_room.current_occupancy += 1
        if change.requested_room.current_occupancy >= change.requested_room.capacity:
            change.requested_room.status = 'Occupied'
        change.requested_room.save()
        
        # Update change request
        change.status = AllocationChangeStatusChoices.COMPLETED
        change.approved_by_caretaker = caretaker
        change.caretaker_approval_date = timezone.now()
        change.caretaker_remarks = remarks
        change.effective_date = timezone.now().date()
        change.save()
    
    # BR-HM-118: Send mandatory room change notification
    send_room_change_notification(change)
    
    return change


def reject_room_change(change_id, rejection_reason):
    """Reject a room change request."""
    change = selectors.get_room_change(change_id)
    if not change:
        raise HostelManagementException(f"Room change {change_id} not found.")
    
    if change.status == AllocationChangeStatusChoices.COMPLETED:
        raise HostelManagementException("Cannot reject a completed room change.")
    
    if change.status == AllocationChangeStatusChoices.REJECTED:
        raise HostelManagementException("Room change is already rejected.")
    
    if not rejection_reason or len(rejection_reason.strip()) < 5:
        raise HostelManagementException("Rejection reason must be at least 5 characters.")
    
    change.status = AllocationChangeStatusChoices.REJECTED
    change.rejection_reason = rejection_reason
    change.save()
    
    # Notify Student
    try:
        notify.send(
            sender=change.student.id.user,
            recipient=change.student.id.user,
            verb="rejected your room change request",
            action_object=change,
            description=f"Your room change request was rejected. Reason: {rejection_reason}.",
            data={"module": "Hostel Management", "url": "hostel-management/room-allocation/changes/"}
        )
    except Exception as e:
        print(f"DEBUG: Room change rejection notification failed: {e}")

    return change


# ══════════════════════════════════════════════════════════════
# HM-WF-105: FINE MANAGEMENT SERVICES
# ══════════════════════════════════════════════════════════════

def issue_fine(student, hostel, fine_type, amount, reason, due_date, issued_by):
    """
    Issue a fine to a student.
    
    Enforces:
    - BR-HM-013: Fine Imposition Validation
    """
    # BR-HM-013: Validate fine data
    if not student or not hostel:
        raise FineValidationError("Student and hostel are required to issue a fine.")
    
    if amount <= 0:
        raise FineValidationError("Fine amount must be greater than zero.")
    
    if due_date < timezone.now().date():
        raise FineValidationError("Due date cannot be in the past.")
    
    if not reason or len(reason.strip()) < 10:
        raise FineValidationError("Fine reason must be at least 10 characters.")
    
    fine = HostelFine.objects.create(
        student=student,
        hostel=hostel,
        fine_type=fine_type,
        amount=Decimal(str(amount)),
        reason=reason,
        due_date=due_date,
        status=FineStatusChoices.PENDING,
        issued_by=issued_by
    )
    
    # Notify Student
    try:
        notify.send(
            sender=issued_by,
            recipient=student.id.user,
            verb="imposed a fine on you",
            action_object=fine,
            description=f"A fine of ₹{amount} has been imposed for: {reason}. Due date: {due_date}.",
            data={"module": "Hostel Management", "url": "hostel-management/fines/"}
        )
    except Exception as e:
        print(f"DEBUG: Fine imposition notification failed: {e}")

    return fine


def pay_fine(fine_id):
    """Mark a fine as paid."""
    fine = selectors.get_fine(fine_id)
    if not fine:
        raise HostelManagementException(f"Fine {fine_id} not found.")
    
    if fine.status != FineStatusChoices.PENDING:
        raise HostelManagementException(
            f"Cannot pay fine in {fine.status} status."
        )
    
    fine.status = FineStatusChoices.PAID
    fine.paid_date = timezone.now().date()
    fine.updated_at = timezone.now()
    fine.save()
    
    # Notify Staff who issued (if applicable)
    if fine.issued_by:
        try:
            notify.send(
                sender=fine.student.id.user,
                recipient=fine.issued_by,
                verb="paid their hostel fine",
                action_object=fine,
                description=f"Student {fine.student} has paid the fine of ₹{fine.amount}.",
                data={"module": "Hostel Management", "url": "hostel-management/fines/"}
            )
        except Exception as e:
            print(f"DEBUG: Fine payment notification failed: {e}")

    return fine


def waive_fine(fine_id, waived_by, waive_reason):
    """Waive a fine (warden authority)."""
    fine = selectors.get_fine(fine_id)
    if not fine:
        raise HostelManagementException(f"Fine {fine_id} not found.")
    
    if fine.status == FineStatusChoices.PAID:
        raise HostelManagementException("Cannot waive an already paid fine.")
    
    if fine.status == FineStatusChoices.CANCELLED:
        raise HostelManagementException("Fine is already cancelled.")
    
    if not waive_reason or len(waive_reason.strip()) < 5:
        raise HostelManagementException("Waive reason must be at least 5 characters.")
    
    fine.status = FineStatusChoices.WAIVED
    fine.waived_by = waived_by
    fine.waive_reason = waive_reason
    fine.updated_at = timezone.now()
    fine.save()
    
    # Notify Student
    try:
        notify.send(
            sender=waived_by,
            recipient=fine.student.id.user,
            verb="waived your fine",
            action_object=fine,
            description=f"Your fine of ₹{fine.amount} has been waived. Reason: {waive_reason}.",
            data={"module": "Hostel Management", "url": "hostel-management/fines/"}
        )
    except Exception as e:
        print(f"DEBUG: Fine waiver notification failed: {e}")

    return fine


def cancel_fine(fine_id):
    """Cancel a fine."""
    fine = selectors.get_fine(fine_id)
    if not fine:
        raise HostelManagementException(f"Fine {fine_id} not found.")
    
    if fine.status in [FineStatusChoices.PAID, FineStatusChoices.WAIVED]:
        raise HostelManagementException(
            f"Cannot cancel a {fine.status} fine."
        )
    fine.status = FineStatusChoices.CANCELLED
    fine.updated_at = timezone.now()
    fine.save()
    
    return fine


# ══════════════════════════════════════════════════════════════
# HM-WF-112: GUEST ROOM BOOKING SERVICES
# ══════════════════════════════════════════════════════════════

def request_guest_room(student, guest_name, guest_phone, arrival_date, departure_date, 
                       purpose, total_guests, guest_email="", guest_address="", 
                       nationality="", rooms_required=1, room_type="single"):
    """
    Request a guest room booking.
    
    Creates a pending guest room booking request that must be approved by staff.
    """
    if not guest_name or len(guest_name.strip()) < 3:
        raise HostelManagementException("Guest name must be at least 3 characters.")
    
    if not guest_phone or len(guest_phone) < 10:
        raise HostelManagementException("Phone number must be at least 10 characters.")
    
    if total_guests <= 0 or total_guests > 100:
        raise HostelManagementException("Total guests must be between 1 and 100.")
    
    if arrival_date >= departure_date:
        raise HostelManagementException("Departure date must be after arrival date.")
    
    duration = (departure_date - arrival_date).days
    if duration > 30:
        raise HostelManagementException("Booking duration cannot exceed 30 days.")
    
    if arrival_date < timezone.now().date():
        raise HostelManagementException("Arrival date cannot be in the past.")
    
    # Get student's primary hall from current allocation
    student_obj = selectors.get_student(student.pk)
    if not student_obj:
        raise HostelManagementException("Student not found.")
    
    current_allocation = selectors.get_student_current_allocation(student_obj)
    if not current_allocation:
        raise HostelManagementException("Student must be allocated to a hostel.")
    
    hall = current_allocation.room.hall    
    # Create booking
    booking = GuestRoomBooking.objects.create(
        student=student_obj,
        hall=hall,
        guest_name=guest_name,
        guest_phone=guest_phone,
        guest_email=guest_email or "",
        guest_address=guest_address or "",
        nationality=nationality or "",
        total_guests=total_guests,
        purpose=purpose,
        arrival_date=arrival_date,
        departure_date=departure_date,
        rooms_required=rooms_required or 1,
        room_type=room_type or "single",
        status=BookingStatusChoices.PENDING,
        booking_date=timezone.now().date()
    )
    
    return booking


def approve_guest_booking(booking_id, approved_by, guest_room_id=None, remarks=""):
    """
    Approve a guest room booking and optionally assign a room.
    """
    booking = selectors.get_guest_booking(booking_id)
    if not booking:
        raise HostelManagementException(f"Guest booking {booking_id} not found.")
    
    if booking.status != BookingStatusChoices.PENDING:
        raise HostelManagementException(
            f"Cannot approve booking in {booking.status} status."
        )
    
    booking.status = BookingStatusChoices.APPROVED
    booking.review_remarks = remarks
    booking.updated_at = timezone.now()
    
    # Assign room if provided
    if guest_room_id:
        guest_room = GuestRoom.objects.filter(id=guest_room_id).first()
        if not guest_room:
            raise HostelManagementException(f"Guest room {guest_room_id} not found.")
        
        # Check if room is available for the requested dates
        if not guest_room.is_vacant:
            raise HostelManagementException("Selected room is not available for requested dates.")
        
        booking.guest_room = guest_room
        guest_room.occupied_till = booking.departure_date
        guest_room.save()
    
    booking.save()
    return booking


def reject_guest_booking(booking_id, rejection_reason):
    """
    Reject a guest room booking request.
    """
    booking = selectors.get_guest_booking(booking_id)
    if not booking:
        raise HostelManagementException(f"Guest booking {booking_id} not found.")
    
    if booking.status != BookingStatusChoices.PENDING:
        raise HostelManagementException(
            f"Cannot reject booking in {booking.status} status."
        )
    
    if not rejection_reason or len(rejection_reason.strip()) < 5:
        raise HostelManagementException("Rejection reason must be at least 5 characters.")
    
    booking.status = BookingStatusChoices.REJECTED
    booking.review_remarks = rejection_reason
    booking.updated_at = timezone.now()
    booking.save()
    
    return booking


def check_in_guest(booking_id):
    """
    Check in a guest (mark as checked in).
    """
    booking = selectors.get_guest_booking(booking_id)
    if not booking:
        raise HostelManagementException(f"Guest booking {booking_id} not found.")
    
    if booking.status != BookingStatusChoices.APPROVED:
        raise HostelManagementException(
            f"Cannot check in booking in {booking.status} status. Must be APPROVED."
        )
    
    if not booking.guest_room:
        raise HostelManagementException("Guest room must be assigned before check-in.")
    
    booking.status = BookingStatusChoices.CHECKED_IN
    booking.checked_in_at = timezone.now()
    booking.updated_at = timezone.now()
    booking.save()
    
    return booking


def check_out_guest(booking_id):
    """
    Check out a guest (mark as checked out).
    """
    booking = selectors.get_guest_booking(booking_id)
    if not booking:
        raise HostelManagementException(f"Guest booking {booking_id} not found.")
    
    if booking.status != BookingStatusChoices.CHECKED_IN:
        raise HostelManagementException(
            f"Cannot check out booking in {booking.status} status. Must be CHECKED_IN."
        )
    
    booking.status = BookingStatusChoices.CHECKED_OUT
    booking.checked_out_at = timezone.now()
    booking.updated_at = timezone.now()
    booking.save()
    
    # Clear room occupancy
    room = booking.room
    if room:
        room.current_occupancy = max(0, room.current_occupancy - 1)
        if room.current_occupancy < room.capacity:
            room.status = 'Available'
        room.save()
    
    return booking


# ...existing code...


# ══════════════════════════════════════════════════════════════
# NOTIFICATION HELPERS - BR-HM-118 & Related
# ══════════════════════════════════════════════════════════════

def assign_warden_to_hostel(hostel, faculty):
    """
    Assign a warden to a hostel (Super Admin only).
    """
    # Remove existing active warden if any
    HostelStaffAssignment.objects.filter(
        hostel=hostel, 
        role=StaffRoleChoices.WARDEN, 
        is_active=True
    ).update(is_active=False)
    
    # Assign new warden
    assignment = HostelStaffAssignment.objects.create(
        hostel=hostel,
        user=faculty.id.user,
        role=StaffRoleChoices.WARDEN,
        is_active=True
    )
    return assignment


def assign_caretaker_to_hostel(hostel, staff):
    """
    Assign a caretaker to a hostel (Super Admin only).
    """
    # Remove existing active caretaker if any
    HostelStaffAssignment.objects.filter(
        hostel=hostel, 
        role=StaffRoleChoices.CARETAKER, 
        is_active=True
    ).update(is_active=False)
    
    # Assign new caretaker
    assignment = HostelStaffAssignment.objects.create(
        hostel=hostel,
        user=staff.id.user,
        role=StaffRoleChoices.CARETAKER,
        is_active=True
    )
    return assignment


def allocate_batch_to_hostel(hostel, academic_batch):
    """
    Allocate an academic batch to a hostel (Super Admin only).
    """
    hostel.save()
    return hostel


def send_room_change_notification(change_request):
    """Implementation of BR-HM-118: Mandatory Room Change Notification."""
    try:
        notify.send(
            sender=change_request.approved_by_caretaker.id.user,
            recipient=change_request.student.id.user,
            verb="completed your room change",
            action_object=change_request,
            description=f"Your room change from {change_request.current_room.room_number} to {change_request.requested_room.room_number} is complete.",
            data={"module": "Hostel Management", "url": "hostel-management/room-allocation/"}
        )
    except Exception as e:
        print(f"DEBUG: Room change completion notification failed: {e}")


# ══════════════════════════════════════════════════════════════
# SUPER ADMIN MANAGEMENT SERVICES
# ══════════════════════════════════════════════════════════════

def assign_warden_to_hostel(hostel, faculty):
    """
    Assign a warden to a hall (Super Admin only).
    
    Args:
        hall: Hall object
        faculty: Faculty object to assign as warden
    
    Returns:
        HallWarden object
    """
    from .models import HallWarden
    
    # Remove existing warden if any
    existing_wardens = HallWarden.objects.filter(hostel=hostel)
    if existing_wardens.exists():
        existing_wardens.delete()
    
    # Assign new warden
    warden = HallWarden.objects.create(
        hostel=hostel,
        faculty=faculty
    )
    return warden


def assign_caretaker_to_hall(hall, staff):
    """
    Assign a caretaker to a hall (Super Admin only).
    
    Args:
        hall: Hall object
        staff: Staff object to assign as caretaker
    
    Returns:
        HallCaretaker object
    """
    from .models import HallCaretaker
    
    # Remove existing caretaker if any
    existing_caretakers = HallCaretaker.objects.filter(hall=hall)
    if existing_caretakers.exists():
        existing_caretakers.delete()
    
    # Assign new caretaker
    caretaker = HallCaretaker.objects.create(
        hall=hall,
        staff=staff
    )
    return caretaker


def allocate_batch_to_hall(hall, academic_batch):
    """
    Allocate an academic batch to a hall (Super Admin only).
    Batch allocation assigns the batch year to a specific hall.
    
    Args:
        hall: Hall object
        academic_batch: AcademicBatch object
    
    Returns:
        Updated Hall object
    """
    hall.assigned_batch = academic_batch
    hall.save()
    return hall


def get_active_batch_years():
    """
    Get all active academic batch years for display and assignment.
    Returns a list of active batches with their details.
    
    Returns:
        List of active batches
    """
    from applications.programme_curriculum.models import Batch
    
    # Get all active batches
    active_batches = Batch.objects.filter(
        running_batch=True
    ).values('id', 'discipline__acronym', 'year').distinct()
    
    return list(active_batches)


def rename_room_in_hall(room, new_room_number, new_block_number=None):
    """
    Rename a room (Warden/Caretaker can rename, changing from sequential 1,2,3 to A101, etc).
    
    Args:
        room: HallRoom object
        new_room_number: New room number (e.g., 'A101')
        new_block_number: New block number (e.g., 'A')
    
    Returns:
        Updated HallRoom object
    """
    room.room_number = new_room_number
    if new_block_number:
        room.block_number = new_block_number
    room.save()
    return room


# ══════════════════════════════════════════════════════════════
# VIEW-FACING SERVICE WRAPPERS
# These functions are called by views.py and delegate to the
# core service functions above.
# ══════════════════════════════════════════════════════════════

def submit_leave_request(student, start_date, end_date, reason, destination=None, contact_phone=None):
    """Wrapper for create_leave_request — called by LeaveListCreateView."""
    return create_leave_request(student, start_date, end_date, reason, destination, contact_phone)



def approve_room_change(change_id, approved_by, remarks=None):
    """Unified room change approval — determines warden vs caretaker step.
    
    approved_by: User object (from request.user)
    Resolves the appropriate Faculty/Staff object based on the approval step.
    """
    from .models import AllocationChangeStatusChoices
    change = selectors.get_room_change(change_id)
    if not change:
        raise HostelManagementException(f"Room change {change_id} not found.")
    
    if change.status == AllocationChangeStatusChoices.REQUESTED:
        # First approval: warden (needs Faculty object)
        faculty = selectors.get_faculty(approved_by.id) if not isinstance(approved_by, Faculty) else approved_by
        if not faculty:
            raise DualApprovalError("Approver must have an active Faculty profile to complete the Warden approval step.")
        return approve_room_change_warden(change_id, faculty, remarks)
    elif change.status == AllocationChangeStatusChoices.APPROVED_WARDEN:
        # Second approval: caretaker (needs Staff/User object)
        staff = selectors.get_staff(approved_by.id) if not isinstance(approved_by, Staff) else approved_by
        if not staff:
            raise DualApprovalError("Approver must have an active Staff profile to complete the Caretaker finalization step.")
        return approve_room_change_caretaker(change_id, staff, remarks)
    else:
        raise HostelManagementException(
            f"Room change cannot be approved in {change.status} status."
        )


def impose_fine(student_id, fine_type, amount, reason, due_date, issued_by):
    """Wrapper for issue_fine — called by FineListCreateView."""
    student = selectors.get_student(student_id)
    if not student:
        raise HostelManagementException("Student not found.")
    
    current_allocation = selectors.get_student_current_allocation(student.pk)
    hall = current_allocation.room.hall if current_allocation and current_allocation.room else None
    if not hall:
        raise HostelManagementException("Student must be allocated to a hall for fines.")
    
    return issue_fine(student, hall, fine_type, amount, reason, due_date, issued_by)


def mark_fine_paid(fine_id, paid_date=None):
    """Wrapper for pay_fine — called by FineMarkPaidView."""
    return pay_fine(fine_id)


def create_staff_schedule(hall_id, staff_id, day_of_week, start_time, end_time, shift_type=None):
    """
    Create a staff schedule — called by StaffScheduleListCreateView.
    Enforces:
    - BR-HM-016: Guard Shift Conflict Prevention
    - BR-HM-027: Security Audit Logging
    """
    from .models import StaffSchedule, Hall
    from django.db.models import Q
    import logging
    
    logger = logging.getLogger(__name__)
    
    hall = Hall.objects.filter(id=hall_id).first()
    if not hall:
        raise HostelManagementException(f"Hall {hall_id} not found.")
    
    from applications.globals.models import Staff
    staff = Staff.objects.filter(id=staff_id).first()
    if not staff:
        raise HostelManagementException(f"Staff {staff_id} not found.")
        
    if start_time >= end_time:
        raise HostelManagementException("Shift end time must be after start time.")
    
    # BR-HM-016: Prevent overlapping shifts
    overlapping = StaffSchedule.objects.filter(
        staff=staff, 
        day_of_week=day_of_week
    ).filter(
        Q(start_time__lt=end_time) & Q(end_time__gt=start_time)
    )
    
    if overlapping.exists():
        raise HostelManagementException("Staff already has an overlapping shift on this day.")
    
    schedule = StaffSchedule.objects.create(
        hall=hall,
        staff=staff,
        day_of_week=day_of_week,
        start_time=start_time,
        end_time=end_time,
        shift_type=shift_type or 'Caretaker'
    )
    
    # BR-HM-027: Security Audit Logging
    logger.info(f"SECURITY AUDIT: Shift created for {staff.id.user.username} at {hall.hall_name} "
                f"on {day_of_week} ({start_time}-{end_time}) by system.")
                
    return schedule


def add_inventory_item(hall_id, item_name, quantity, unit_cost, remarks=None):
    """
    Add an inventory item — called by InventoryListCreateView.
    Enforces:
    - BR-HM-030: Resource Request Validation
    - BR-HM-031: Inventory Audit Trail
    """
    from .models import HostelInventory, Hall
    import logging
    
    logger = logging.getLogger(__name__)
    
    hall = Hall.objects.filter(id=hall_id).first()
    if not hall:
        raise HostelManagementException(f"Hall {hall_id} not found.")
        
    # BR-HM-030: Quantity must be positive
    if quantity <= 0:
        raise HostelManagementException("Quantity must be a positive integer.")
    
    item = HostelInventory.objects.create(
        hall=hall,
        item_name=item_name,
        quantity=quantity,
        unit_cost=unit_cost,
        remarks=remarks
    )
    
    # BR-HM-031: Inventory Audit Trail
    logger.info(f"INVENTORY AUDIT: Added item {item_name} (Qty: {quantity}) to {hall.hall_name}.")
    
    return item


# ══════════════════════════════════════════════════════════════
# NEW FEATURES: VACATIONS & EXTENDED STAYS (BR-HM-015 - BR-HM-062)
# ══════════════════════════════════════════════════════════════

def process_room_vacation(vacation_id, action, remarks=None):
    """
    Process Room Vacation Request.
    Enforces:
    - BR-HM-015: Room Vacation Prerequisites (no fines)
    - BR-HM-028: Vacation Finalization
    - BR-HM-023: Room Availability update on deallocation
    """
    from .models import HostelFine, FineStatusChoices, RoomAllocationStatusChoices
    
    vacation = selectors.get_room_vacation(vacation_id)
    if not vacation:
        raise HostelManagementException("Vacation request not found.")
        
    student = vacation.student
    
    if action == 'approve':
        # BR-HM-015: Check outstanding fines
        outstanding_fines = HostelFine.objects.filter(
            student=student, 
            status=FineStatusChoices.PENDING
        ).exists()
        if outstanding_fines:
            raise HostelManagementException("Student cannot vacate: Outstanding fines exist.")
            
        vacation.status = 'approved'
        vacation.remarks = remarks
        vacation.save()
        
        # BR-HM-023 & BR-HM-028: Update room availability and release allocation
        current_alloc = selectors.get_student_current_allocation(student)
        if current_alloc and current_alloc.room:
            room = current_alloc.room
            room.current_occupancy = max(0, room.current_occupancy - 1)
            if room.current_occupancy == 0:
                room.status = 'available'
            room.save()
            
            current_alloc.status = RoomAllocationStatusChoices.VACANT
            from django.utils import timezone
            current_alloc.release_date = timezone.now().date()
            current_alloc.save()
            
    elif action == 'verify':
        vacation.status = 'verified'
        vacation.remarks = remarks
        vacation.save()
        
    return vacation


def create_extended_stay(student, start_date, end_date, reason):
    """
    Submit Extended Stay.
    Enforces:
    - BR-HM-061: Extended Stay Eligibility (Must have active alloc)
    - BR-HM-062: Vacation Period Validation
    """
    from .models import ExtendedStayApplication
    
    # BR-HM-061: Active hostel allocation is required
    current_allocation = selectors.get_student_current_allocation(student.pk)
    if not current_allocation or current_allocation.status != RoomAllocationStatusChoices.ALLOCATED:
        raise HostelManagementException("Student must have active hostel allocation for extended stay.")
        
    # BR-HM-062: Date validation
    from django.utils import timezone
    today = timezone.now().date()
    if start_date < today:
        raise HostelManagementException("Start date cannot be in the past.")
    if end_date <= start_date:
        raise HostelManagementException("End date must be after start date.")
        
    duration = (end_date - start_date).days
    if duration > 45:
        raise HostelManagementException("Extended stay cannot exceed 45 days.")
        
    stay = ExtendedStayApplication.objects.create(
        student=student,
        start_date=start_date,
        end_date=end_date,
        reason=reason,
        status='pending'
    )
    return stay
    
    def update_inventory(inventory_id, quantity=None, remarks=None):
        """
        Update an inventory item — called by InventoryRetrieveUpdateView.
        Enforces:
        - BR-HM-030: Resource Request Validation
        - BR-HM-021: Discrepancy Logging
        - BR-HM-031: Inventory Audit Trail
        """
        import logging
        logger = logging.getLogger(__name__)
    
        item = selectors.get_inventory_item(inventory_id)
        if not item:
            raise HostelManagementException(f"Inventory item {inventory_id} not found.")
        
        old_qty = item.quantity
        
        if quantity is not None:
            if quantity < 0:
                raise HostelManagementException("Quantity cannot be negative.")
            item.quantity = quantity
        
        if remarks is not None:
            item.remarks = remarks
            
        item.save()
        
        # BR-HM-021: Discrepancy logging
        if quantity is not None and quantity < old_qty:
            logger.warning(
                f"DISCREPANCY LOG: {item.item_name} at {item.hall.hall_name} decreased from {old_qty} to {quantity}. Remarks: {remarks}"
            )
            
        # BR-HM-031: Audit Trail
        logger.info(f"INVENTORY AUDIT: Updated item {item.item_name} to Qty: {quantity}")
        
        return item
# --------------------------------------------------------------
# HM-WF-103: ACCOMMODATION REQUEST & ALLOTMENT SERVICES
# --------------------------------------------------------------

@transaction.atomic
def create_accommodation_request(student, window_id, preferred_hostel_type, preferred_room_type):
    from .models import AccommodationApplicationWindow, AccommodationRequest
    window = AccommodationApplicationWindow.objects.get(id=window_id)
    if not window.is_open:
        raise ApplicationWindowError(f'Application window {window.name} is currently closed.')
    request, created = AccommodationRequest.objects.get_or_create(
        student=student, window=window,
        defaults={'preferred_hostel_type': preferred_hostel_type, 'preferred_room_type': preferred_room_type}
    )
    if not created:
        request.preferred_hostel_type = preferred_hostel_type
        request.preferred_room_type = preferred_room_type
        request.save()
    return request

@transaction.atomic
def perform_bulk_allotment_logic(request_ids, allotted_by):
    from django.db.models import F
    from .models import AccommodationRequest, Hostel, Room, RoomAllotment, HostelStatusChoices, RoomSetupStatusChoices
    results = {'success': [], 'failed': []}
    requests = AccommodationRequest.objects.filter(id__in=request_ids, status=AccommodationRequest.Status.PENDING)
    for req in requests:
        try:
            suitable_hostels = Hostel.objects.filter(type=req.preferred_hostel_type, status=HostelStatusChoices.ACTIVE)
            allotted = False
            for hostel in suitable_hostels:
                available_room = Room.objects.filter(hostel=hostel, current_occupancy__lt=F('capacity'), status=RoomSetupStatusChoices.AVAILABLE).first()
                if available_room:
                    RoomAllotment.objects.filter(student=req.student, is_active=True).update(is_active=False)
                    RoomAllotment.objects.create(student=req.student, room=available_room, hostel=hostel, allotted_by=allotted_by)
                    available_room.current_occupancy += 1
                    available_room.save()
                    req.status = AccommodationRequest.Status.ALLOTTED
                    req.save()
                    results['success'].append(req.id)
                    allotted = True
                    break
            if not allotted:
                results['failed'].append({'id': req.id, 'reason': 'No capacity available'})
        except Exception as e:
            results['failed'].append({'id': req.id, 'reason': str(e)})
    return results

def perform_bulk_batch_allocation(hall_id, programme_category, admission_year, gender, allotted_by):
    """
    Perform sequential bulk batch allocation.
    - Matches students by category, admission year, and gender.
    - Only considers students without active allotments.
    - Fills rooms floor-by-floor, topping up partially filled rooms first.
    """
    from django.db import transaction
    from django.db.models import F
    from django.shortcuts import get_object_or_404
    from applications.academic_information.models import Student
    from .models import Hostel, Room, RoomAllotment, RoomSetupStatusChoices

    # 1. Map programme category to actual programme strings
    category_map = {
        'UG': ['B.Tech', 'B.Des'],
        'PG': ['M.Des', 'PhD'],
        'M.Tech': ['M.Tech']
    }
    programmes = category_map.get(programme_category, [])

    with transaction.atomic():
        # 2. Identify target Hostel and verify gender
        hostel = get_object_or_404(Hostel, hall_id=hall_id)
        
        # Guard: Check for existing active residents
        if RoomAllotment.objects.filter(hostel=hostel, is_active=True).exists():
             raise ValueError(
                 f"Bulk allocation cannot be performed on {hostel.name} because it already has active residents. "
                 "Please ensure the hostel is 'Emptied Out' before a fresh batch allocation."
             )

        # Gender mismatch check (prevent cross-gender bulk allocation)
        if gender == 'M' and hostel.type == 'Girl':
             raise ValueError(f"Hostel {hall_id} is for Girls, but Male students selected.")
        if gender == 'F' and hostel.type == 'Boy':
             raise ValueError(f"Hostel {hall_id} is for Boys, but Female students selected.")

        # 3. Fetch eligible students (Sequential by their ID/username)
        students = Student.objects.filter(
            programme__in=programmes,
            batch=admission_year,
            id__sex=gender
        ).exclude(
            room_allotments__is_active=True
        ).select_related('id__user').order_by('id__user__username')
        
        # Load students into memory to avoid N+1 query performance bottleneck during iteration
        students_list = list(students)
        total_students = len(students_list)
        if total_students == 0:
            return {'count': 0, 'total_found': 0, 'message': 'No eligible students found for this batch.'}

        # 4. Fetch available rooms, sorted by floor then room number
        # We fill partially occupied rooms first within the same floor priority
        available_rooms = Room.objects.filter(
            hostel=hostel,
            status=RoomSetupStatusChoices.AVAILABLE,
            current_occupancy__lt=F('capacity')
        ).order_by('floor', 'room_number')

        allotted_count = 0
        student_idx = 0
        
        for room in available_rooms:
            if student_idx >= total_students:
                break
                
            while room.current_occupancy < room.capacity and student_idx < total_students:
                student = students_list[student_idx]
                
                # Create Allotment
                RoomAllotment.objects.create(
                    student=student,
                    room=room,
                    hostel=hostel,
                    allotted_by=allotted_by,
                    is_active=True
                )
                
                room.current_occupancy += 1
                allotted_count += 1
                student_idx += 1
            
            # Update room status if full
            if room.current_occupancy >= room.capacity:
                room.status = RoomSetupStatusChoices.OCCUPIED
            room.save()
            
        return {
            'count': allotted_count,
            'total_found': total_students,
            'message': f"Successfully allotted {allotted_count} of {total_students} students."
        }


@transaction.atomic
def delete_room_allotment(allotment_id):
    """
    Permanently delete a room allotment and reconcile occupancy.
    - Used by Super Admins to manually clear allocations.
    """
    # Use global RoomSetupStatusChoices, fallback to string if necessary
    try:
        AVAILABLE = RoomSetupStatusChoices.AVAILABLE
    except (AttributeError, NameError):
        AVAILABLE = "Available"

    # Fetch allotment without select_for_update to avoid transaction isolation issues in some environments
    allotment = RoomAllotment.objects.filter(id=allotment_id).first()
    if not allotment:
        raise HostelManagementException(f"Allocation record {allotment_id} not found.")

    room = allotment.room
    if not room:
        # If room is missing, we still delete the allotment but log a warning
        allotment.delete()
        return True

    # Update room occupancy safely
    room.current_occupancy = max(0, (room.current_occupancy or 1) - 1)
    
    # If room is now below capacity, mark as available
    if room.current_occupancy < room.capacity:
        room.status = AVAILABLE
        
    room.save()

    # Delete the allotment record
    allotment.delete()
    
    return True


# ══════════════════════════════════════════════════════════════
# HM-WF-105: FINE MANAGEMENT SERVICES
# ══════════════════════════════════════════════════════════════

def validate_fine_evidence(file):
    """
    Validate fine evidence document (BR-HM-022).
    - Max 5MB
    - Allowed Types: JPEG, PNG, PDF
    """
    if not file:
        return True
    
    # 5MB Limit
    if file.size > 5 * 1024 * 1024:
        raise FineValidationError("Evidence file size exceeds 5MB limit.")
    
    # Type Check
    ext = file.name.split('.')[-1].lower()
    if ext not in ['jpg', 'jpeg', 'png', 'pdf']:
        raise FineValidationError("Unsupported evidence file type. Use JPG, PNG or PDF.")
    
    return True


@transaction.atomic
def impose_fine(student, hostel, imposed_by, category, amount, reason, evidence=None, extra_details=None):
    """
    Impose a disciplinary fine on a student (HM-UC-016).
    Enforces:
    - BR-HM-013.a: Amount must be > 0
    - BR-HM-013.b: Category must be valid
    - BR-HM-013.c: Reason must not be empty
    - BR-HM-014.a: Initial status is always 'pending'
    - BR-HM-022: Evidence validation
    """
    # Validation (BR-HM-013)
    if amount <= 0:
        raise FineValidationError("Fine amount must be greater than zero.")
    
    if not category or category not in FineCategoryChoices.values:
        raise FineValidationError("Invalid violation category.")
    
    if not reason or not reason.strip():
        raise FineValidationError("Reason for fine must be provided.")
    
    # Evidence Validation (BR-HM-022)
    if evidence:
        validate_fine_evidence(evidence)
    
    # Create Fine
    fine = HostelFine.objects.create(
        student=student,
        hostel=hostel,
        imposed_by=imposed_by,
        category=category,
        amount=amount,
        reason=reason,
        evidence=evidence,
        status=FineStatusChoices.PENDING
    )
    
    # Save Extra Details
    if extra_details:
        for detail_type, content in extra_details.items():
            FineExtraDetail.objects.create(
                fine=fine,
                detail_type=detail_type,
                detail_json=content
            )
            
    # Notify Student (Optional requirement based on implementation plan)
    try:
        notify.send(
            imposed_by,
            recipient=student.id.user,
            verb="imposed a fine",
            target=fine,
            description=f"A fine of ₹{amount} has been imposed for {category}.",
            data={"module": "Hostel Management", "url": "hostel-management/fines/"}
        )
    except Exception as e:
        print(f"Notification failed: {e}")
        
    return fine


@transaction.atomic
def mark_fine_as_paid(fine_id, user):
    """
    Mark a fine as paid (HM-UC-017).
    """
    fine = HostelFine.objects.select_for_update().filter(id=fine_id).first()
    if not fine:
        raise HostelManagementException("Fine record not found.")
        
    if fine.status == FineStatusChoices.PAID:
        return fine
        
    fine.status = FineStatusChoices.PAID
    fine.paid_date = timezone.now()
    fine.save()
    
    return fine


# ══════════════════════════════════════════════════════════════
# MODERN INVENTORY SERVICES
# ══════════════════════════════════════════════════════════════

@transaction.atomic
def record_inventory_inspection(item_id, actual_qty, condition, performer, remarks=""):
    """
    Record an inventory inspection (HM-UC-020).
    - BR-HM-021.a: Create discrepancy if actual != expected or condition Damaged/Missing
    - BR-HM-031.a: Write InventoryAuditLog
    """
    from .models import InventoryItem, InventoryDiscrepancy, InventoryAuditLog, DiscrepancyType, InventoryCondition
    
    item = InventoryItem.objects.select_for_update().filter(id=item_id).first()
    if not item:
        raise HostelManagementException("Inventory item not found.")
    
    old_qty = item.current_quantity
    old_condition = item.condition
    expected_qty = item.expected_quantity
    
    # Check for discrepancy
    has_discrepancy = (actual_qty != expected_qty) or (condition in [InventoryCondition.DAMAGED, InventoryCondition.MISSING])
    
    if has_discrepancy:
        d_type = DiscrepancyType.MISSING
        if condition == InventoryCondition.DAMAGED:
            d_type = DiscrepancyType.DAMAGED
        elif actual_qty < expected_qty:
            d_type = DiscrepancyType.MISSING
        elif actual_qty == 0 and expected_qty > 0:
            d_type = DiscrepancyType.DEPLETED

        InventoryDiscrepancy.objects.create(
            item=item,
            hostel=item.hostel,
            discrepancy_type=d_type,
            expected_qty=expected_qty,
            actual_qty=actual_qty,
            condition=condition,
            remarks=remarks or f"Automated discrepancy reported during inspection. Condition: {condition}",
            reported_by=performer
        )

    # Write Audit Log
    InventoryAuditLog.objects.create(
        item=item,
        hostel=item.hostel,
        action="Inspected",
        old_qty=old_qty,
        new_qty=actual_qty,
        old_condition=old_condition,
        new_condition=condition,
        performed_by=performer,
        remarks=remarks
    )

    # Update item
    item.current_quantity = actual_qty
    item.condition = condition
    item.last_inspected_at = timezone.now()
    item.save()
    
    return item


@transaction.atomic
def update_inventory_record(item_id, quantity, condition, performer, remarks=""):
    """
    Direct inventory update (HM-UC-021).
    - BR-HM-031.a: Write InventoryAuditLog
    """
    from .models import InventoryItem, InventoryAuditLog
    
    item = InventoryItem.objects.select_for_update().filter(id=item_id).first()
    if not item:
        raise HostelManagementException("Inventory item not found.")
    
    old_qty = item.current_quantity
    old_condition = item.condition
    
    # Write Audit Log
    InventoryAuditLog.objects.create(
        item=item,
        hostel=item.hostel,
        action="Updated",
        old_qty=old_qty,
        new_qty=quantity,
        old_condition=old_condition,
        new_condition=condition,
        performed_by=performer,
        remarks=remarks
    )

    # Update item
    item.current_quantity = quantity
    item.condition = condition
    item.save()
    
    return item


def submit_resource_request(hostel_id, requester, request_type, category, item_name, quantity, justification):
    """
    Submit resource procurement request (HM-UC-022).
    - BR-HM-030.a/b: Mandatory fields and quantity validation
    """
    from .models import ResourceRequest, Hostel
    
    if not all([hostel_id, request_type, item_name, quantity, justification]):
        raise HostelManagementException("All fields (hostel, type, item, quantity, justification) are mandatory.")
        
    if quantity <= 0:
        raise HostelManagementException("Quantity must be a positive integer.")
        
    hostel = Hostel.objects.filter(hall_id=hostel_id).first()
    if not hostel:
        raise HostelManagementException("Hostel not found.")
        
    request = ResourceRequest.objects.create(
        hostel=hostel,
        requested_by=requester,
        request_type=request_type,
        category=category,
        item_name=item_name,
        quantity=quantity,
        justification=justification
    )
    return request


@transaction.atomic
def review_resource_request(request_id, reviewer, status, remarks=""):
    """
    Review resource request (HM-UC-023) - Admin only.
    """
    from .models import ResourceRequest, ResourceRequestStatus
    
    request = ResourceRequest.objects.select_for_update().filter(id=request_id).first()
    if not request:
        raise HostelManagementException("Resource request not found.")
        
    if status not in [ResourceRequestStatus.APPROVED, ResourceRequestStatus.REJECTED]:
        raise HostelManagementException("Invalid status for review.")
        
    request.status = status
    request.reviewed_by = reviewer
    request.reviewed_at = timezone.now()
    if remarks:
        request.justification += f"\n\nReviewer Remarks: {remarks}"
    request.save()
    
    # Auto-sync with Inventory on Approval
    if status == ResourceRequestStatus.APPROVED:
        from .models import InventoryItem, InventoryCondition, InventoryAuditLog
        
        # Try to find existing item in this hostel
        item, created = InventoryItem.objects.get_or_create(
            hostel=request.hostel,
            name=request.item_name,
            defaults={
                'category': request.category,
                'unit': 'Pcs', # Default unit
                'expected_quantity': request.quantity,
                'current_quantity': request.quantity,
                'condition': InventoryCondition.GOOD
            }
        )
        
        if not created:
            item.expected_quantity += request.quantity
            item.current_quantity += request.quantity
            item.save()
            
        # Log the automated update
        InventoryAuditLog.objects.create(
            item=item,
            hostel=request.hostel,
            action="Procurement Linked",
            old_qty=item.current_quantity - request.quantity if not created else 0,
            new_qty=item.current_quantity,
            old_condition=item.condition,
            new_condition=item.condition,
            performed_by=reviewer,
            remarks=f"Automatically updated via approved Resource Request #{request.id}. Stock increased by {request.quantity}."
        )

    return request


@transaction.atomic
def bulk_upload_inventory(hostel_id, excel_file, user):
    """
    Bulk upload inventory items from Excel (HM-WF-108).
    - Enforces strict categories (BR-HM-030.c)
    - Updates expected_quantity for existing items (BR-HM-030.d)
    - Creates audit logs for all changes
    """
    import pandas as pd
    from .models import InventoryItem, InventoryCategory, Hostel, InventoryAuditLog

    hostel = Hostel.objects.filter(hall_id=hostel_id).first()
    if not hostel:
        raise HostelManagementException(f"Hostel {hostel_id} not found.")

    try:
        df = pd.read_excel(excel_file)
    except Exception as e:
        raise HostelManagementException(f"Failed to read Excel file: {str(e)}")

    required_cols = ['item_name', 'category', 'unit', 'expected_quantity']
    actual_cols = df.columns.tolist()
    for col in required_cols:
        if col not in actual_cols:
            raise HostelManagementException(f"Missing mandatory column: {col}")

    created_count = 0
    updated_count = 0
    errors = []

    valid_categories = [c[0] for c in InventoryCategory.choices]

    for index, row in df.iterrows():
        try:
            name = str(row['item_name']).strip()
            cat = str(row['category']).strip()
            unit = str(row['unit']).strip()
            exp_qty = int(row['expected_quantity'])
            curr_qty = int(row['current_quantity']) if 'current_quantity' in row and not pd.isna(row['current_quantity']) else 0

            if cat not in valid_categories:
                errors.append(f"Row {index+2}: Invalid category '{cat}'")
                continue

            # Robust upsert logic
            from .models import InventoryCondition
            item = InventoryItem.objects.filter(hostel=hostel, name=name).first()
            
            if item:
                item.category = cat
                item.unit = unit
                item.expected_quantity = exp_qty
                if 'current_quantity' in row and not pd.isna(row['current_quantity']):
                    item.current_quantity = curr_qty
                item.save()
                updated_count += 1
            else:
                item = InventoryItem.objects.create(
                    hostel=hostel,
                    name=name,
                    category=cat,
                    unit=unit,
                    expected_quantity=exp_qty,
                    current_quantity=curr_qty,
                    condition=InventoryCondition.GOOD
                )
                created_count += 1

            InventoryAuditLog.objects.create(
                item=item,
                hostel=hostel,
                action="Bulk Uploaded",
                new_qty=item.current_quantity,
                new_condition=item.condition,
                performed_by=user,
                remarks="Imported via Excel upload"
            )

        except Exception as e:
            errors.append(f"Row {index+2}: {str(e)}")

    return {
        'created': created_count,
        'updated': updated_count,
        'errors': errors
    }


@transaction.atomic
def resolve_discrepancy(discrepancy_id, user):
    """
    Resolve a discrepancy by syncing inventory to reported actual quantity.
    """
    from .models import InventoryDiscrepancy, InventoryAuditLog, InventoryCondition
    
    discrepancy = InventoryDiscrepancy.objects.select_for_update().filter(id=discrepancy_id).first()
    if not discrepancy:
        raise HostelManagementException("Discrepancy not found.")
        
    item = discrepancy.item
    old_qty = item.current_quantity
    
    # Sync inventory permanently: set baseline to verified count and reset condition to GOOD
    item.expected_quantity = discrepancy.actual_qty
    item.current_quantity = discrepancy.actual_qty
    item.condition = InventoryCondition.GOOD 
    item.last_inspected_at = timezone.now()
    item.save()
    
    # Log resolution
    InventoryAuditLog.objects.create(
        item=item,
        hostel=item.hostel,
        action="Discrepancy Resolved",
        old_qty=old_qty,
        new_qty=item.current_quantity,
        old_condition=item.condition,
        new_condition=item.condition,
        performed_by=user,
        remarks=f"Resolved discrepancy: {discrepancy.remarks}. Stock reset to {item.expected_quantity} ({item.condition})."
    )
    
    # Remove discrepancy record
    discrepancy.delete()
    
    return item


# ══════════════════════════════════════════════════════════════
# HM-WF-110: NOTICE BOARD SERVICES
# ══════════════════════════════════════════════════════════════

@transaction.atomic
def create_notice(user, data, attachment=None):
    """
    Create a new notice and handle priority side-effects.
    """
    from rest_framework.exceptions import PermissionDenied
    from .selectors import is_user_warden_or_caretaker, list_assigned_hostels
    
    # Permission check (Warden/Caretaker only)
    if not (user.is_superuser or is_user_warden_or_caretaker(user)):
        raise PermissionDenied("Only staff members can post notices.")

    hostel_id = data.get('hostel_id') or data.get('hostel')
    if hostel_id == 'all' or not hostel_id:
        hostel_id = None
        
    # If hostel_id is a model object (legacy or direct from serializer)
    if hasattr(hostel_id, 'pk'):
        hostel_id = hostel_id.pk
        
    # Global Notice Check: Only Super Admins can post to all hostels
    if hostel_id is None and not user.is_superuser:
         raise PermissionDenied("Only Super Admins can post global notices visible to all hostels.")

    if hostel_id and not user.is_superuser:
        assigned = list_assigned_hostels(user).filter(hall_id=hostel_id).exists()
        if not assigned:
            raise PermissionDenied(f"You are not authorized to post notices for hostel {hostel_id}.")

    # Generate unique UID
    import uuid
    notice_uid = f"NTC-{uuid.uuid4().hex[:8].upper()}"

    notice = Notice.objects.create(
        hostel_id=hostel_id,
        created_by=user,
        title=data.get('title'),
        description=data.get('description'),
        priority=data.get('priority', NoticePriority.NORMAL),
        start_date=data.get('start_date'),
        end_date=data.get('end_date'),
        status=data.get('status', NoticeStatus.PUBLISHED),
        attachment=attachment,
        notice_uid=notice_uid
    )

    # BR-HM-033: Immediate push notification for Urgent notices
    if notice.priority == NoticePriority.URGENT and notice.status == NoticeStatus.PUBLISHED:
        _trigger_urgent_notice_notification(notice)

    return notice


@transaction.atomic
def update_notice(notice_id, data, user, attachment=None):
    """Update an existing notice."""
    notice = Notice.objects.get(id=notice_id)
    
    if not user.is_superuser and notice.created_by != user:
         raise PermissionError("You can only edit notices created by yourself.")

    # Update fields
    notice.title = data.get('title', notice.title)
    notice.description = data.get('description', notice.description)
    notice.priority = data.get('priority', notice.priority)
    notice.start_date = data.get('start_date', notice.start_date)
    notice.end_date = data.get('end_date', notice.end_date)
    notice.status = data.get('status', notice.status)
    
    if attachment:
        notice.attachment = attachment
        
    notice.save()
    return notice


@transaction.atomic
def delete_notice(notice_id, user):
    """Delete a notice."""
    notice = Notice.objects.get(id=notice_id)
    if not user.is_superuser and notice.created_by != user:
         raise PermissionError("You can only delete notices created by yourself.")
    notice.delete()
    return True


@transaction.atomic
def mark_notice_as_read(notice_id, user):
    """Record that a student has read a notice."""
    from .selectors import get_student
    student = get_student(user)
    if not student:
        return None
        
    read_status, created = NoticeReadStatus.objects.get_or_create(
        notice_id=notice_id,
        student=student
    )
    return read_status


@transaction.atomic
def archive_expired_notices():
    """Daily task to archive notices past their end date."""
    now = timezone.now().date()
    updated_count = Notice.objects.filter(
        status=NoticeStatus.PUBLISHED,
        end_date__lt=now
    ).update(status=NoticeStatus.ARCHIVED)
    return updated_count


def _trigger_urgent_notice_notification(notice):
    """
    Send push notification for urgent hostel notice.
    Implementation of BR-HM-033.
    """
    from .models import RoomAllotment
    
    # Identify target users
    if notice.hostel:
        # Students in specific hostel
        target_users = list(RoomAllotment.objects.filter(
            hostel=notice.hostel, is_active=True
        ).values_list('student__id__user', flat=True))
    else:
        # Global notice - limited to 100 students for performance if not using Celery
        target_users = list(RoomAllotment.objects.filter(
            is_active=True
        ).values_list('student__id__user', flat=True)[:100])

    try:
        from django.contrib.auth.models import User
        recipients = User.objects.filter(id__in=target_users)
        
        # Batch send
        for recipient in recipients:
            notify.send(
                sender=notice.created_by,
                recipient=recipient,
                verb="posted an urgent notice",
                action_object=notice,
                description=f"URGENT: {notice.title}",
                data={"module": "Hostel Management", "url": "hostel-management/notice-board/"}
            )
    except Exception as e:
        print(f"DEBUG: Urgent notice notification failed: {e}")
# ══════════════════════════════════════════════════════════════
# HM-WF-112: GUEST ROOM SERVICES (CHUNK 12)
# ══════════════════════════════════════════════════════════════

@transaction.atomic
def register_guest_room_service(hostel, room, caretaker_user):
    if GuestRoom.objects.filter(room=room).exists():
        raise GuestRoomBookingError(f"Room {room.room_number} is already in the guest registry.")
    
    # Ensure room is completely empty and available
    if room.current_occupancy > 0 or room.status != 'Available':
        raise GuestRoomBookingError(
            f"Room {room.room_number} is not suitable for guest designation. "
            "It must be completely empty and in 'Available' status."
        )
    
    guest_room = GuestRoom.objects.create(
        hostel=hostel,
        room=room,
        is_active=True
    )
    return guest_room


@transaction.atomic
def update_guest_policy_service(hostel, caretaker_user, **policy_data):
    """Configure or update guest booking policies for a hostel."""
    from .models import GuestRoomPolicy
    
    policy, created = GuestRoomPolicy.objects.get_or_create(
        hostel=hostel,
        defaults={'updated_by': caretaker_user}
    )
    
    for key, value in policy_data.items():
        if hasattr(policy, key):
            setattr(policy, key, value)
    
    policy.updated_by = caretaker_user
    policy.save()
    return policy


@transaction.atomic
def create_guest_booking_service(student, hostel, guest_data, check_in_date, check_out_date):
    """
    Submit a guest room booking request.
    Enforces:
    - Overlap checking
    - Policy rate application
    """
    from .selectors import get_guest_policy, get_guest_room_availability
    
    # 1. Eligibility: Check if student has no active damage fines (simplified rule)
    if selectors.count_student_unpaid_fines(student.id.id) > 2:
        raise GuestRoomPolicyError("Student has too many unpaid fines to request guest rooms.")

    # 2. Date Validation
    if check_in_date >= check_out_date:
        raise GuestRoomPolicyError("Check-out date must be after check-in date.")
    
    if check_in_date < timezone.now().date():
        raise GuestRoomPolicyError("Check-in date cannot be in the past.")

    # 3. Policy & Rate
    policy = get_guest_policy(hostel.hall_id)
    if not policy:
        raise GuestRoomPolicyError("This hostel has not configured a guest room policy yet.")
    
    # 4. Find Available Guest Room
    available_guest_rooms = GuestRoom.objects.filter(hostel=hostel, is_active=True)
    target_room = None
    for gr in available_guest_rooms:
        if get_guest_room_availability(gr.id, check_in_date, check_out_date):
            target_room = gr.room
            break
            
    if not target_room:
        raise GuestRoomAvailabilityError("No guest rooms are available for the selected dates.")

    # 5. UID Generation
    import uuid
    booking_uid = f"GRB-{uuid.uuid4().hex[:8].upper()}"
    
    # 6. Calculate Duration & Charges
    nights = (check_out_date - check_in_date).days
    total_charges = nights * policy.per_night_rate

    booking = GuestRoomBooking.objects.create(
        student=student,
        hostel=hostel,
        room=target_room,
        booking_uid=booking_uid,
        guest_name=guest_data.get('guest_name'),
        guest_phone=guest_data.get('guest_phone'),
        guest_email=guest_data.get('guest_email'),
        guest_address=guest_data.get('guest_address', ''),
        nationality=guest_data.get('nationality', ''),
        visit_purpose=guest_data.get('visit_purpose'),
        check_in_date=check_in_date,
        check_out_date=check_out_date,
        per_night_rate=policy.per_night_rate,
        total_charges=total_charges,
        status=BookingStatusChoices.PENDING
    )
    
    # Notify Caretaker
    try:
        caretaker = selectors.get_hostel_caretaker(hostel.hall_id)
        if caretaker:
            notify.send(
                sender=student.id.user,
                recipient=caretaker.user,
                verb="submitted a guest room booking request",
                action_object=booking,
                description=f"New guest room booking {booking_uid} requested by {student}.",
                data={"module": "Hostel Management", "url": "hostel-management/guest-booking/"}
            )
    except Exception as e:
        print(f"DEBUG: Guest room booking notification failed: {e}")

    return booking


@transaction.atomic
def process_booking_decision_service(booking_id, caretaker_user, decision, remarks="", room_id=None):
    """Caretaker approves or rejects a booking request."""
    booking = GuestRoomBooking.objects.select_for_update().get(id=booking_id)
    
    if booking.status != BookingStatusChoices.PENDING:
        raise GuestRoomBookingError("Can only process pending bookings.")
    
    if decision == 'approved':
        booking.status = BookingStatusChoices.APPROVED
        if room_id:
            try:
                from .models import GuestRoom
                gr = GuestRoom.objects.get(id=room_id)
                booking.room = gr.room
            except GuestRoom.DoesNotExist:
                raise GuestRoomBookingError("Invalid room selected.")
    elif decision == 'rejected':
        booking.status = BookingStatusChoices.REJECTED
    else:
        raise GuestRoomBookingError(f"Invalid decision '{decision}'. Must be 'approved' or 'rejected'.")
        
    booking.caretaker_remarks = remarks
    booking.save()
    
    # Notify Student
    notify.send(
        sender=caretaker_user,
        recipient=booking.student.id.user,
        verb=f"{decision}d your guest room booking",
        action_object=booking,
        description=f"Your booking {booking.booking_uid} has been {decision}d.",
        data={"module": "Hostel Management", "url": "hostel-management/guest-booking/"}
    )
    
    return booking


@transaction.atomic
def process_checkin_service(booking_id, caretaker_user, id_proof_type, id_proof_number):
    """Record guest check-in with ID verification."""
    booking = GuestRoomBooking.objects.select_for_update().get(id=booking_id)
    
    if booking.status != BookingStatusChoices.APPROVED:
        raise GuestRoomBookingError("Only approved bookings can be checked in.")
    
    booking.status = BookingStatusChoices.CHECKED_IN
    booking.id_proof_type = id_proof_type
    booking.id_proof_number = id_proof_number
    booking.id_verified_at = timezone.now()
    
    # Update check-in date to the actual date
    actual_in_date = timezone.now().date()
    booking.check_in_date = actual_in_date
    if booking.check_out_date <= actual_in_date:
        from datetime import timedelta
        booking.check_out_date = actual_in_date + timedelta(days=1)
        
    booking.save()

    # Update Room Occupancy
    room = booking.room
    room.current_occupancy = min(room.capacity, room.current_occupancy + 1)
    if room.current_occupancy >= room.capacity:
        room.status = 'Occupied'
    room.save()

    return booking


@transaction.atomic
def process_checkout_service(booking_id, caretaker_user, condition_remarks, damage_severity, damage_charge=Decimal('0.00')):
    """
    Record guest check-out and inspection.
    Automatically issues a fine if damage is recorded.
    """
    from .models import GuestRoomInspection, DamageSeverityChoices, FineCategoryChoices
    
    booking = GuestRoomBooking.objects.select_for_update().get(id=booking_id)
    
    if booking.status != BookingStatusChoices.CHECKED_IN:
        raise GuestRoomBookingError("Booking must be in checked-in status for check-out.")
    
    # 1. Create Inspection Record
    inspection = GuestRoomInspection.objects.create(
        booking=booking,
        conducted_by=caretaker_user,
        damage_description=condition_remarks,
        severity=damage_severity,
        estimated_repair_cost=damage_charge,
        damage_found=(damage_severity != 'None')
    )
    
    # 2. Update Booking Status and recalculate duration
    actual_out_date = timezone.now().date()
    booking.check_out_date = actual_out_date
    nights = (actual_out_date - booking.check_in_date).days
    nights = max(1, nights) # Minimum 1 night charge
    
    booking.total_charges = nights * booking.per_night_rate
    booking.status = BookingStatusChoices.COMPLETED
    booking.save()

    # 3. Update Room Occupancy
    room = booking.room
    room.current_occupancy = max(0, room.current_occupancy - 1)
    if room.current_occupancy < room.capacity:
        room.status = 'Available'
    room.save()
    
    # 3. Automated Fine if Damage Exists
    if damage_severity != DamageSeverityChoices.NONE or damage_charge > 0:
        impose_fine(
            student=booking.student,
            hostel=booking.hostel,
            imposed_by=caretaker_user,
            category=FineCategoryChoices.PROPERTY_DAMAGE,
            amount=damage_charge,
            reason=f"Damage detected during guest room check-out ({booking.booking_uid}). {condition_remarks}"
        )
    
    return booking, inspection


@transaction.atomic
def assign_staff_to_hostel(hostel, staff_user, role, start_date, assigned_by, end_date=None):
    """
    Assign a staff member (Warden/Caretaker) to a hostel.
    Enforces business rules:
    - BR-HM-034: A staff member can only have ONE active hostel assignment across the system.
    - BR-HM-035: A hostel can only have ONE active Warden/Caretaker (depending on role).
    """
    # 1. Rule: One active assignment per staff member globally
    active_assignment = HostelStaffAssignment.objects.filter(
        user=staff_user, is_active=True
    ).select_related('hostel').first()

    if active_assignment:
        raise HostelManagementException(
            f"Staff member {staff_user.get_full_name() or staff_user.username} is already "
            f"actively assigned to {active_assignment.hostel.name}. "
            "Please remove their current assignment before re-assigning."
        )

    # 2. Rule: Check if the hostel already has an active staff of this role
    role_label = "Warden" if role == StaffRoleChoices.WARDEN else "Caretaker"
    existing_role_active = HostelStaffAssignment.objects.filter(
        hostel=hostel, role=role, is_active=True
    ).exists()

    if existing_role_active:
         raise HostelManagementException(
            f"This hostel already has an active {role_label} assigned. "
            "Please remove the existing assignment first."
        )

    # 3. Create the assignment
    assignment = HostelStaffAssignment.objects.create(
        hostel=hostel,
        user=staff_user,
        role=role,
        start_date=start_date,
        end_date=end_date,
        is_active=True,
        assigned_by=assigned_by
    )

    # 4. Write audit log
    action_type = 'WARDEN_ASSIGNED' if role == StaffRoleChoices.WARDEN else 'CARETAKER_ASSIGNED'
    HostelAuditLog.objects.create(
        hostel=hostel,
        action=action_type,
        performed_by=assigned_by,
        detail_json={
            'user_id': staff_user.id,
            'user_name': staff_user.get_full_name() or staff_user.username,
            'start_date': str(assignment.start_date),
            'role': role
        }
    )

    return assignment


def transfer_student_fines(student, new_hostel):
    """
    Transfers all unpaid/unwaived fines from previous hostels to the new hostel.
    This ensures the new hostel's warden/caretaker can see and manage them.
    - BR-HM-036: Fine Transfer on Re-allotment
    """
    unpaid_fines = HostelFine.objects.filter(
        student=student,
        status=FineStatusChoices.PENDING
    )
    
    count = unpaid_fines.update(hostel=new_hostel)
    return count


@transaction.atomic
def process_bulk_hostel_vacation(hostel_ids, performed_by):
    """
    Vacates multiple hostels (Semester End Process).
    - Unallocates all students
    - Resets room occupancy
    - Cancels pending leaves/complaints
    - Logs audit trail
    """
    target_hostels = Hostel.objects.filter(hall_id__in=hostel_ids)
    
    affected_count = 0
    for hostel in target_hostels:
        # 0. Pre-check: Skip if hostel has no active allotments, pending leaves, or complaints
        active_count = RoomAllotment.objects.filter(hostel=hostel, is_active=True).count()
        pending_leaves = LeaveRequest.objects.filter(
            hostel=hostel,
            status__in=[LeaveStatusChoices.PENDING, LeaveStatusChoices.APPROVED]
        ).count()
        pending_complaints = HostelComplaint.objects.filter(
            hostel=hostel,
            status__in=[ComplaintStatusChoices.SUBMITTED, ComplaintStatusChoices.IN_PROGRESS]
        ).count()

        if active_count == 0 and pending_leaves == 0 and pending_complaints == 0:
            continue

        affected_count += 1

        # 1. Deactivate all allotments
        active_allotments = RoomAllotment.objects.filter(
            hostel=hostel, is_active=True
        ).select_related('student__id__user')
        
        student_users = [a.student.id.user for a in active_allotments]
        
        active_allotments.update(
            is_active=False,
            vacated_at=timezone.now()
        )
        
        # 2. Reset room occupancy
        hostel.rooms_setup.update(
            current_occupancy=0,
            status='Available'
        )
        
        # 3. Cancel pending/approved leaves
        LeaveRequest.objects.filter(
            hostel=hostel,
            status__in=[LeaveStatusChoices.PENDING, LeaveStatusChoices.APPROVED]
        ).update(
            status=LeaveStatusChoices.CANCELLED,
            decision_remarks="Cancelled due to semester-end hostel vacation.",
            updated_at=timezone.now()
        )
        
        # 4. Close pending complaints
        HostelComplaint.objects.filter(
            hostel=hostel,
            status__in=[ComplaintStatusChoices.SUBMITTED, ComplaintStatusChoices.IN_PROGRESS]
        ).update(
            status=ComplaintStatusChoices.CLOSED,
            resolution_remarks="Closed due to semester-end hostel vacation.",
            updated_at=timezone.now()
        )
        
        # 5. Audit Log
        HostelAuditLog.objects.create(
            hostel=hostel,
            action='HOSTEL_VACATED',
            performed_by=performed_by,
            detail_json={
                'allotments_deactivated': active_count,
                'reason': 'Semester End Bulk Vacation'
            }
        )
        
        # 6. Notify students
        for user in student_users:
            from .services import notify
            notify.send(
                sender=performed_by,
                recipient=user,
                verb="notified hostel vacation",
                description=f"Your room allotment in {hostel.name} has been vacated due to semester end."
            )

    return affected_count


# ══════════════════════════════════════════════════════════════
# SECURITY MANAGEMENT SERVICES
# ══════════════════════════════════════════════════════════════

def register_security_guard(hostel=None, name=None, employee_id=None, contact=None, user=None, **kwargs):
    """
    Register a new security guard.
    Warden registers guards for their own hostel.
    """
    if not hostel:
         raise ValueError("Hostel is required for guard registration.")

    return SecurityGuard.objects.create(
        hostel=hostel,
        name=name,
        employee_id=employee_id,
        contact=contact,
        user=user,
        **kwargs
    )


def create_guard_shift(assigned_by, guard, hostel, shift_type, date, start_time, end_time):
    """
    Assign a shift to a guard.
    - BR-HM-016.a: Conflict Detection (overlaps)
    - Immutable Audit Logging
    """
    # 1. Conflict Check
    conflict = selectors.get_guard_conflict(guard.id, date, start_time, end_time)
    if conflict:
        raise GuardShiftConflictError(
            f"Guard {guard.name} is already assigned to a shift ({conflict.shift_type}) at this time."
        )

    with transaction.atomic():
        shift = GuardShift.objects.create(
            guard=guard,
            hostel=hostel,
            shift_type=shift_type,
            date=date,
            start_time=start_time,
            end_time=end_time,
            assigned_by=assigned_by
        )

        _log_shift_action(
            guard=guard,
            hostel=hostel,
            action=ShiftActionChoices.ASSIGNED,
            performed_by=assigned_by,
            detail_json={
                "shift_id": shift.id,
                "type": shift_type,
                "date": str(date),
                "start": str(start_time),
                "end": str(end_time)
            }
        )

    return shift


def update_guard_shift(shift_id, performed_by, **kwargs):
    """Update an existing shift with conflict re-validation."""
    shift = GuardShift.objects.get(pk=shift_id)
    
    date = kwargs.get('date', shift.date)
    start_time = kwargs.get('start_time', shift.start_time)
    end_time = kwargs.get('end_time', shift.end_time)
    
    # Check conflict excluding itself
    conflict = selectors.get_guard_conflict(shift.guard_id, date, start_time, end_time, exclude_shift_id=shift_id)
    if conflict:
        raise GuardShiftConflictError("Update failed: User has a conflicting shift at the new time.")

    with transaction.atomic():
        for field, value in kwargs.items():
            setattr(shift, field, value)
        shift.save()

        _log_shift_action(
            guard=shift.guard,
            hostel=shift.hostel,
            action=ShiftActionChoices.MODIFIED,
            performed_by=performed_by,
            detail_json={"shift_id": shift.id, "changes": kwargs}
        )
    
    return shift


def delete_guard_shift(shift_id, performed_by):
    """Remove a shift and log the action."""
    shift = GuardShift.objects.get(pk=shift_id)
    with transaction.atomic():
        _log_shift_action(
            guard=shift.guard,
            hostel=shift.hostel,
            action=ShiftActionChoices.REMOVED,
            performed_by=performed_by,
            detail_json={"shift_id": shift_id, "type": shift.shift_type, "date": str(shift.date)}
        )
        shift.delete()


def _log_shift_action(guard, hostel, action, performed_by, detail_json):
    """Internal: Maintain immutable security audit trail."""
    # Ensure guard info is preserved even if the record is later deleted
    data = detail_json or {}
    if guard:
        data.update({
            "guard_name": guard.name,
            "guard_employee_id": guard.employee_id
        })
        
    ShiftScheduleLog.objects.create(
        guard=guard,
        hostel=hostel,
        action=action,
        performed_by=performed_by,
        detail_json=data
    )


def update_security_guard(guard_id, performed_by=None, **kwargs):
    """Update security guard profile and log the action."""
    guard = SecurityGuard.objects.get(pk=guard_id)
    
    # Track changed fields for logging
    changes = {}
    for field, value in kwargs.items():
        if hasattr(guard, field) and field not in ['id', 'created_at', 'hostel']:
            old_value = getattr(guard, field)
            if old_value != value:
                changes[field] = {"old": str(old_value), "new": str(value)}
                setattr(guard, field, value)
    
    if changes:
        with transaction.atomic():
            guard.save()
            _log_shift_action(
                guard=guard,
                hostel=guard.hostel,
                action=ShiftActionChoices.MODIFIED,
                performed_by=performed_by,
                detail_json={"action": "Profile Update", "changes": changes}
            )
    return guard


def delete_security_guard(guard_id):
    """Remove a security guard from the registry."""
    SecurityGuard.objects.filter(pk=guard_id).delete()

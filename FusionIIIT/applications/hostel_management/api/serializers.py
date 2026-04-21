"""
Serializers - DRF serializers with field-level validation only.

CRITICAL RULES:
- NO business logic here
- Only field-level validate_<fieldname> methods
- Only I/O serialization and validation
- Use validate_<field>() for field-level validation only
- Custom validators must NOT involve database queries beyond basic existence checks

Supports Workflows:
- HM-WF-101: Leave Management
- HM-WF-102: Complaint Management
- HM-WF-103: Room Allocation
- HM-WF-104: Room Changes
- HM-WF-105: Fine Management
"""

from rest_framework import serializers
from django.utils import timezone

from ..models import (
    LeaveRequest, StudentAttendanceRecord, HostelComplaint,
    RoomAllocationChange,
    HostelFine,
    StaffSchedule,
    HostelNoticeBoard,
    HostelInventory,
    GuestRoom,
    GuestRoomBooking,
    GuestRoomPolicy,
    GuestRoomInspection,
    LeaveStatusChoices,
    ComplaintCategoryChoices,
    AccommodationApplicationWindow,
    AccommodationRequest,
    RoomAllotment,
    Hostel,
    Room,
    StaffRoleChoices,
    HostelStatusChoices,
    HostelStaffAssignment,
    HostelAuditLog,
    ComplaintHistory,
    FineExtraDetail,
    InventoryItem,
    InventoryDiscrepancy,
    InventoryAuditLog as InventoryAuditTrail,
    ResourceRequest,
    InventoryCondition,
    ResourceRequestStatus,
    Notice, NoticeReadStatus, SecurityGuard,
    GuardShift, ShiftScheduleLog, RoomVacationRequest, ExtendedStayApplication
)
from applications.academic_information.models import Student


# ══════════════════════════════════════════════════════════════
# HOSTEL SETUP FOUNDATION SERIALIZERS
# ══════════════════════════════════════════════════════════════

class RoomSetupSerializer(serializers.ModelSerializer):
    """Read-only serializer for Room (new Hostel→Room system)."""
    class Meta:
        model = Room
        fields = [
            'id', 'hostel', 'room_number', 'floor', 'capacity',
            'current_occupancy', 'status'
        ]
        read_only_fields = fields


class HostelSetupSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for Hostel list/retrieve.
    Includes computed fields for active warden and caretaker names,
    and room counts.
    """
    active_warden = serializers.SerializerMethodField()
    active_caretaker = serializers.SerializerMethodField()
    total_rooms = serializers.SerializerMethodField()
    occupied_rooms = serializers.SerializerMethodField()
    created_by_name = serializers.SerializerMethodField()

    class Meta:
        model = Hostel
        fields = [
            'hall_id', 'name', 'type', 'total_capacity', 'floor_count',
            'room_config_json', 'status', 'created_by', 'created_by_name',
            'created_at', 'updated_at',
            'active_warden', 'active_caretaker', 'total_rooms', 'occupied_rooms'
        ]
        read_only_fields = fields

    def get_active_warden(self, obj):
        assignment = obj.staff_assignments.filter(
            role=StaffRoleChoices.WARDEN, is_active=True
        ).select_related('user').first()
        if assignment:
            return {
                'id': assignment.id,
                'user_id': assignment.user.id,
                'name': assignment.user.get_full_name() or assignment.user.username,
                'email': assignment.user.email,
                'start_date': assignment.start_date,
            }
        return None

    def get_active_caretaker(self, obj):
        assignment = obj.staff_assignments.filter(
            role=StaffRoleChoices.CARETAKER, is_active=True
        ).select_related('user').first()
        if assignment:
            return {
                'id': assignment.id,
                'user_id': assignment.user.id,
                'name': assignment.user.get_full_name() or assignment.user.username,
                'email': assignment.user.email,
                'start_date': assignment.start_date,
            }
        return None

    def get_total_rooms(self, obj):
        return obj.rooms_setup.count()

    def get_occupied_rooms(self, obj):
        return obj.rooms_setup.filter(current_occupancy__gt=0).count()

    def get_created_by_name(self, obj):
        if obj.created_by:
            return obj.created_by.get_full_name() or obj.created_by.username
        return None


class HostelCreateSerializer(serializers.ModelSerializer):
    """
    Create serializer for Hostel.

    Validates:
    - No duplicate hostel name
    - Positive total_capacity
    - Valid room_config_json schema
    - BR-HM-025: Config is source of truth
    """
    class Meta:
        model = Hostel
        fields = [
            'hall_id', 'name', 'type', 'total_capacity', 'floor_count', 'room_config_json'
        ]
        extra_kwargs = {
            'hall_id': {'required': True, 'allow_blank': False}
        }


class RoomSerializer(serializers.ModelSerializer):
    """
    Serializer for the Room model.
    """
    class Meta:
        from ..models import Room
        model = Room
        fields = [
            'id', 'room_number', 'floor', 'capacity', 
            'current_occupancy', 'status', 'hostel'
        ]
        read_only_fields = fields

    def validate_name(self, value):
        if not value or len(value.strip()) < 2:
            raise serializers.ValidationError("Hostel name must be at least 2 characters.")
        if Hostel.objects.filter(name__iexact=value.strip()).exists():
            raise serializers.ValidationError(f"A hostel named '{value}' already exists.")
        return value.strip()

    def validate_total_capacity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Total capacity must be greater than 0.")
        return value

    def validate_floor_count(self, value):
        if value <= 0:
            raise serializers.ValidationError("Floor count must be at least 1.")
        return value

    def validate_room_config_json(self, value):
        """Validate room_config_json schema."""
        if not value:
            return value

        if not isinstance(value, dict):
            raise serializers.ValidationError("room_config_json must be a JSON object.")

        floors = value.get('floors')
        if floors is None:
            return value  # Empty config is allowed

        if not isinstance(floors, list):
            raise serializers.ValidationError("'floors' must be a list.")

        for i, floor_cfg in enumerate(floors):
            if not isinstance(floor_cfg, dict):
                raise serializers.ValidationError(f"Floor config at index {i} must be an object.")
            if 'floor' not in floor_cfg:
                raise serializers.ValidationError(f"Floor config at index {i} must have 'floor' field.")
            if 'rooms_per_floor' not in floor_cfg:
                raise serializers.ValidationError(f"Floor config at index {i} must have 'rooms_per_floor' field.")
            if floor_cfg.get('rooms_per_floor', 0) <= 0:
                raise serializers.ValidationError(f"Floor {floor_cfg['floor']}: rooms_per_floor must be positive.")
            if floor_cfg.get('capacity_per_room', 1) <= 0:
                raise serializers.ValidationError(f"Floor {floor_cfg['floor']}: capacity_per_room must be positive.")

        return value


class HostelStatusSerializer(serializers.Serializer):
    """
    Serializer for hostel status transitions.

    Validates transition rules before save:
    - BR-HM-008.a: Block deactivation if hostel has occupied rooms
    - BR-HM-008.b: Block activation if no active Warden OR no active Caretaker
    - BR-HM-019.a: Same as BR-HM-008.b
    """
    status = serializers.ChoiceField(choices=HostelStatusChoices.choices)

    def validate_status(self, value):
        hostel = self.context.get('hostel')
        if not hostel:
            return value

        current_status = hostel.status

        # Same status — no-op
        if current_status == value:
            raise serializers.ValidationError(f"Hostel is already in '{value}' status.")

        # BR-HM-008.a: Block deactivation if occupied rooms exist
        if value == HostelStatusChoices.INACTIVE:
            occupied_rooms = hostel.rooms_setup.filter(current_occupancy__gt=0).exists()
            if occupied_rooms:
                raise serializers.ValidationError(
                    "Cannot deactivate hostel: there are rooms with current occupants. "
                    "All rooms must be vacated before deactivation."
                )

        # BR-HM-008.b / BR-HM-019.a: Block activation without staff
        if value == HostelStatusChoices.ACTIVE:
            has_warden = hostel.staff_assignments.filter(
                role=StaffRoleChoices.WARDEN, is_active=True
            ).exists()
            has_caretaker = hostel.staff_assignments.filter(
                role=StaffRoleChoices.CARETAKER, is_active=True
            ).exists()

            if not has_warden:
                raise serializers.ValidationError(
                    "Cannot activate hostel: no active Warden assigned. "
                    "Assign at least one Warden before activating."
                )
            if not has_caretaker:
                raise serializers.ValidationError(
                    "Cannot activate hostel: no active Caretaker assigned. "
                    "Assign at least one Caretaker before activating."
                )

        return value


class StaffAssignmentSerializer(serializers.ModelSerializer):
    """
    Read-only serializer for staff assignment display.
    """
    user_name = serializers.SerializerMethodField()
    user_email = serializers.EmailField(source='user.email', read_only=True)
    hostel_name = serializers.CharField(source='hostel.name', read_only=True)
    assigned_by_name = serializers.SerializerMethodField()

    class Meta:
        model = HostelStaffAssignment
        fields = [
            'id', 'hostel', 'hostel_name', 'user', 'user_name', 'user_email',
            'role', 'start_date', 'end_date', 'is_active',
            'assigned_by', 'assigned_by_name', 'created_at'
        ]
        read_only_fields = fields

    def get_user_name(self, obj):
        return obj.user.get_full_name() or obj.user.username

    def get_assigned_by_name(self, obj):
        if obj.assigned_by:
            return obj.assigned_by.get_full_name() or obj.assigned_by.username
        return None


class StaffAssignmentCreateSerializer(serializers.Serializer):
    """
    Create serializer for staff assignment.

    Validates:
    - User exists
    - Role is valid
    - BR-HM-019.b: Warns (does not block) if staff has concurrent active assignments
    """
    user_id = serializers.IntegerField()
    role = serializers.ChoiceField(choices=StaffRoleChoices.choices)
    start_date = serializers.DateField()
    end_date = serializers.DateField(required=False, allow_null=True)

    def validate_user_id(self, value):
        from django.contrib.auth.models import User
        if not User.objects.filter(id=value).exists():
            raise serializers.ValidationError(f"User with ID {value} does not exist.")
        return value

    def validate(self, data):
        from django.contrib.auth.models import User
        user = User.objects.get(id=data['user_id'])

        # Check for multiple concurrent assignments (BR-HM-034 - Hard Block)
        active_assignment = HostelStaffAssignment.objects.filter(
            user=user, is_active=True
        ).select_related('hostel').first()

        if active_assignment:
            raise serializers.ValidationError({
                "user_id": f"This user is already actively assigned to {active_assignment.hostel.name}. "
                           "Please remove their current assignment before re-assigning."
            })

        if data.get('end_date') and data['end_date'] < data['start_date']:
            raise serializers.ValidationError("End date must be after start date.")

        return data


class HostelAuditLogSerializer(serializers.ModelSerializer):
    """Read-only serializer for audit log display."""
    performed_by_name = serializers.SerializerMethodField()
    hostel_name = serializers.CharField(source='hostel.name', read_only=True)

    class Meta:
        model = HostelAuditLog
        fields = [
            'id', 'hostel', 'hostel_name', 'action', 'performed_by',
            'performed_by_name', 'detail_json', 'timestamp'
        ]
        read_only_fields = fields

    def get_performed_by_name(self, obj):
        if obj.performed_by:
            return obj.performed_by.get_full_name() or obj.performed_by.username
        return None



# ══════════════════════════════════════════════════════════════
# LEAVE SERIALIZERS (HM-WF-101)
# ══════════════════════════════════════════════════════════════


# ══════════════════════════════════════════════════════════════
# LEAVE SERIALIZERS (HM-WF-101)
# ══════════════════════════════════════════════════════════════

class LeaveRequestSerializer(serializers.ModelSerializer):
    """Read-only serializer for Leave Request details."""
    student_name = serializers.CharField(source='student.id.user.username', read_only=True)
    decided_by_name = serializers.CharField(source='decided_by.username', read_only=True, allow_null=True)
    
    class Meta:
        model = LeaveRequest
        fields = [
            'id', 'student', 'student_name', 'hostel', 'start_date', 'end_date',
            'reason', 'status', 'documents', 'decision_remarks',
            'decided_by', 'decided_by_name', 'created_at', 'updated_at'
        ]
        read_only_fields = fields


class LeaveRequestCreateSerializer(serializers.ModelSerializer):
    """Create serializer for Leave Request with mandatory documents validation."""
    
    class Meta:
        model = LeaveRequest
        fields = ['start_date', 'end_date', 'reason', 'documents']
    
    def validate_start_date(self, value):
        """Validate start_date is not in past."""
        if value < timezone.now().date():
            raise serializers.ValidationError("Start date cannot be in the past.")
        return value
    
    def validate_end_date(self, value):
        """Validate end_date is in future."""
        if value < timezone.now().date():
            raise serializers.ValidationError("End date must be in the future.")
        return value
    
    def validate(self, data):
        """Validate range, duration, and mandatory documents."""
        if data['start_date'] > data['end_date']:
            raise serializers.ValidationError("End date must be after or equal to start date.")
        
        duration = (data['end_date'] - data['start_date']).days
        if duration > 90:
            raise serializers.ValidationError("Leave duration cannot exceed 90 days.")
        
        if not data.get('reason') or len(data['reason'].strip()) < 3:
            raise serializers.ValidationError("Reason must be at least 3 characters long.")

        if not data.get('documents'):
            raise serializers.ValidationError("Supporting documents are mandatory for leave submission.")
        
        return data


class LeaveRequestDecisionSerializer(serializers.Serializer):
    """Serializer for Leave decision (Approve/Reject)."""
    status = serializers.ChoiceField(choices=[LeaveStatusChoices.APPROVED, LeaveStatusChoices.REJECTED])
    decision_remarks = serializers.CharField(required=True, allow_blank=False, max_length=500)


# ══════════════════════════════════════════════════════════════
# COMPLAINT SERIALIZERS (HM-WF-102)
# ══════════════════════════════════════════════════════════════

class ComplaintHistorySerializer(serializers.ModelSerializer):
    """Timeline history for complaint status changes."""
    changed_by_name = serializers.CharField(source='changed_by.get_full_name', read_only=True)
    
    class Meta:
        model = ComplaintHistory
        fields = [
            'id', 'old_status', 'new_status', 'remarks', 
            'changed_by', 'changed_by_name', 'timestamp'
        ]
        read_only_fields = fields


class HostelComplaintSerializer(serializers.ModelSerializer):
    """Read-only serializer for Complaint details with history."""
    student_name = serializers.CharField(source='student.id.user.get_full_name', read_only=True)
    assigned_to_name = serializers.CharField(source='assigned_to_user.get_full_name', read_only=True, allow_null=True)
    history = ComplaintHistorySerializer(many=True, read_only=True)
    
    class Meta:
        model = HostelComplaint
        fields = [
            'id', 'complaint_uid', 'student', 'student_name', 
            'hostel', 'category', 'description', 
            'status', 'assigned_to_user', 'assigned_to_name', 
            'resolution_remarks', 'history', 'created_at', 'updated_at', 'resolved_at',
            'attachments'
        ]
        read_only_fields = fields


class HostelComplaintCreateSerializer(serializers.ModelSerializer):
    """Create serializer for Complaint."""
    
    class Meta:
        model = HostelComplaint
        fields = ['category', 'description', 'attachments']
    
    def validate_description(self, value):
        """Validate description length (BR-HM-110)."""
        if not value or len(value.strip()) < 20:
            raise serializers.ValidationError("Description must be at least 20 characters.")
        return value
    
    def validate_category(self, value):
        """Validate category is valid."""
        if value not in dict(ComplaintCategoryChoices.choices):
            raise serializers.ValidationError("Invalid complaint category.")
        return value


class HostelComplaintResolveSerializer(serializers.Serializer):
    """Serializer for resolving a complaint."""
    resolution_remarks = serializers.CharField(min_length=3, max_length=1000)


class HostelComplaintEscalateSerializer(serializers.Serializer):
    """Serializer for escalating complaint to warden."""
    reason = serializers.CharField(min_length=3, max_length=500)


# ══════════════════════════════════════════════════════════════
# HM-WF-103: ACCOMMODATION SERIALIZERS
# ══════════════════════════════════════════════════════════════

class AccommodationApplicationWindowSerializer(serializers.ModelSerializer):
    """Serializer for accommodation application windows."""
    is_open = serializers.BooleanField(read_only=True)

    class Meta:
        model = AccommodationApplicationWindow
        fields = ['id', 'name', 'start_date', 'end_date', 'is_active', 'is_open', 'created_at']
        read_only_fields = ['id', 'is_open', 'created_at']


class AccommodationRequestSerializer(serializers.ModelSerializer):
    """Serializer for accommodation requests."""
    student_name = serializers.CharField(source='student.id.user.get_full_name', read_only=True)
    roll_number = serializers.CharField(source='student.id.id', read_only=True)
    window_name = serializers.CharField(source='window.name', read_only=True)

    class Meta:
        model = AccommodationRequest
        fields = [
            'id', 'student', 'student_name', 'roll_number',
            'window', 'window_name', 'preferred_hostel_type',
            'preferred_room_type', 'status', 'submitted_at'
        ]
        read_only_fields = ['id', 'student', 'status', 'submitted_at', 'student_name', 'window_name', 'roll_number']

    def validate(self, data):
        """Ensure student doesn't have multiple requests for the same window."""
        request = self.context.get('request')
        if request and request.method == 'POST':
            student = getattr(request.user, 'student', None)
            if not student:
                raise serializers.ValidationError("Only students can submit requests.")
            
            # This is also enforced by unique_together in Model
            window = data.get('window')
            if AccommodationRequest.objects.filter(student=student, window=window).exists():
                raise serializers.ValidationError("You have already submitted a request for this window.")
        
        return data


class RoomAllotmentSerializer(serializers.ModelSerializer):
    """Serializer for active room allotments."""
    student_id = serializers.CharField(source='student.id.user.username', read_only=True)
    student_name = serializers.CharField(source='student.id.user.get_full_name', read_only=True)
    hostel_name = serializers.CharField(source='hostel.name', read_only=True)
    room_number = serializers.CharField(source='room.room_number', read_only=True)
    room = RoomSetupSerializer(read_only=True)

    class Meta:
        model = RoomAllotment
        fields = [
            'id', 'student', 'student_id', 'student_name', 'room', 'room_number', 'hostel',
            'hostel_name', 'allotted_by', 'allotted_at', 'vacated_at', 'is_active'
        ]
        read_only_fields = fields




# ══════════════════════════════════════════════════════════════
# ROOM ALLOCATION CHANGE SERIALIZERS (HM-WF-104)
# ══════════════════════════════════════════════════════════════

class RoomAllocationChangeSerializer(serializers.ModelSerializer):
    """Serializer for Room Change - both read and write operations."""
    student_name = serializers.CharField(source='student.id.user.username', read_only=True)
    current_room_number = serializers.CharField(source='current_room.room_number', read_only=True)
    requested_room_number = serializers.CharField(source='requested_room.room_number', read_only=True, allow_null=True)
    warden_name = serializers.CharField(source='approved_by_warden.id.user.username', read_only=True, allow_null=True)
    caretaker_name = serializers.CharField(source='approved_by_caretaker.id.user.username', read_only=True, allow_null=True)
    
    class Meta:
        model = RoomAllocationChange
        fields = [
            'id', 'student', 'student_name', 'current_room', 'current_room_number',
            'requested_room', 'requested_room_number', 'reason', 'status',
            'requested_date', 'effective_date', 'approved_by_warden', 'warden_name',
            'warden_remarks', 'approved_by_caretaker', 'caretaker_name', 'caretaker_remarks',
            'rejection_reason', 'created_at', 'updated_at'
        ]
        read_only_fields = [
            'id', 'student', 'student_name', 'current_room', 'current_room_number',
            'requested_room_number', 'status', 'requested_date', 'effective_date',
            'approved_by_warden', 'warden_name', 'warden_remarks', 'approved_by_caretaker',
            'caretaker_name', 'caretaker_remarks', 'rejection_reason', 'created_at', 'updated_at'
        ]
    
    def validate_reason(self, value):
        """Validate reason length."""
        if not value or len(value.strip()) < 3:
            raise serializers.ValidationError("Reason must be at least 3 characters.")
        return value


class RoomAllocationChangeApprovalSerializer(serializers.Serializer):
    """Serializer for Room Change approval."""
    approve = serializers.BooleanField()
    remarks = serializers.CharField(required=False, allow_blank=True, max_length=500)
    effective_date = serializers.DateField(required=False)


# ══════════════════════════════════════════════════════════════
# FINE SERIALIZERS (HM-WF-105)
# ══════════════════════════════════════════════════════════════

class FineExtraDetailSerializer(serializers.ModelSerializer):
    """Serializer for category-specific fine details."""
    class Meta:
        model = FineExtraDetail
        fields = ['detail_type', 'detail_json']


class HostelFineSerializer(serializers.ModelSerializer):
    """Read-only serializer for HostelFine with nested details."""
    student_name = serializers.CharField(source='student.id.user.get_full_name', read_only=True)
    student_roll = serializers.CharField(source='student.id.id', read_only=True)
    imposed_by_name = serializers.CharField(source='imposed_by.get_full_name', read_only=True)
    waived_by_name = serializers.CharField(source='waived_by.get_full_name', read_only=True)
    hostel_name = serializers.CharField(source='hostel.name', read_only=True)
    extra_details = FineExtraDetailSerializer(many=True, read_only=True)
    
    class Meta:
        model = HostelFine
        fields = [
            'id', 'fine_uid', 'student', 'student_name', 'student_roll',
            'hostel', 'hostel_name', 'category', 'amount', 'reason',
            'evidence', 'status', 'imposed_date', 'paid_date',
            'imposed_by', 'imposed_by_name', 'waived_by', 'waived_by_name',
            'waive_reason', 'updated_at', 'extra_details'
        ]
        read_only_fields = fields


class StudentMinimalSerializer(serializers.ModelSerializer):
    """Minimal student serializer for analytical views."""
    name = serializers.CharField(source='id.user.get_full_name', read_only=True)
    roll_number = serializers.CharField(source='id.id', read_only=True)
    
    class Meta:
        model = Student
        fields = ['id', 'name', 'roll_number']
        read_only_fields = fields


class ImposeFineSerializer(serializers.ModelSerializer):
    """Serializer for imposing a new fine (HM-UC-016)."""
    student_id = serializers.CharField(write_only=True)
    extra_fields = serializers.JSONField(required=False, write_only=True)
    
    class Meta:
        model = HostelFine
        fields = ['student_id', 'category', 'amount', 'reason', 'evidence', 'extra_fields']
    
    def validate_amount(self, value):
        if value <= 0:
            raise serializers.ValidationError("Fine amount must be greater than zero (BR-HM-013.a).")
        return value

    def validate_reason(self, value):
        if not value or not value.strip():
            raise serializers.ValidationError("Reason for fine cannot be empty (BR-HM-013.c).")
        return value


class HostelFinePaymentSerializer(serializers.Serializer):
    """Serializer for marking fine as paid."""
    paid_date = serializers.DateField()
    
    def validate_paid_date(self, value):
        """Validate paid_date is not in future."""
        if value > timezone.now().date():
            raise serializers.ValidationError("Paid date cannot be in the future.")
        return value


class HostelFineWaiverSerializer(serializers.Serializer):
    """Serializer for waiving fine."""
    waive_reason = serializers.CharField(max_length=500)


# ══════════════════════════════════════════════════════════════
# STAFF SCHEDULE SERIALIZERS (HM-WF-107)
# ══════════════════════════════════════════════════════════════

class StaffScheduleSerializer(serializers.ModelSerializer):
    """Serializer for Staff Schedule."""
    hall_name = serializers.CharField(source='hall.hall_name', read_only=True)
    staff_name = serializers.CharField(source='staff.id.user.username', read_only=True)
    
    class Meta:
        model = StaffSchedule
        fields = [
            'id', 'hall', 'hall_name', 'staff', 'staff_name', 'day_of_week',
            'start_time', 'end_time', 'shift_type', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'created_at', 'updated_at', 'hall_name', 'staff_name']


# ══════════════════════════════════════════════════════════════
# LEGACY INVENTORY SERIALIZERS (To be deprecated)
# ══════════════════════════════════════════════════════════════

class HostelInventorySerializer(serializers.ModelSerializer):
    """Serializer for Hostel Inventory."""
    hall_name = serializers.CharField(source='hostel.name', read_only=True)
    
    class Meta:
        model = HostelInventory
        fields = [
            'id', 'hostel', 'hall_name', 'item_name', 'quantity', 'unit_cost',
            'remarks', 'last_updated', 'created_at'
        ]
        read_only_fields = ['id', 'created_at', 'hall_name']


# ══════════════════════════════════════════════════════════════
# MODERN INVENTORY SERIALIZERS (HM-WF-108)
# ══════════════════════════════════════════════════════════════

class InventoryAuditTrailSerializer(serializers.ModelSerializer):
    """Read-only serializer for inventory audit trail."""
    performed_by_name = serializers.CharField(source='performed_by.get_full_name', read_only=True)
    item_name = serializers.CharField(source='item.name', read_only=True)
    hostel_name = serializers.CharField(source='hostel.name', read_only=True)

    class Meta:
        model = InventoryAuditTrail
        fields = [
            'id', 'item', 'item_name', 'hostel', 'hostel_name', 'action',
            'old_qty', 'new_qty', 'old_condition', 'new_condition',
            'performed_by', 'performed_by_name', 'remarks', 'timestamp'
        ]
        read_only_fields = fields


class InventoryItemSerializer(serializers.ModelSerializer):
    """Read-only serializer for inventory item details."""
    hostel_name = serializers.CharField(source='hostel.name', read_only=True)

    class Meta:
        model = InventoryItem
        fields = [
            'id', 'hostel', 'hostel_name', 'name', 'category', 'unit',
            'expected_quantity', 'current_quantity', 'condition',
            'last_inspected_at', 'created_at', 'updated_at'
        ]
        read_only_fields = fields


class InventoryInspectionSerializer(serializers.Serializer):
    """Serializer for recording an inspection (HM-UC-020)."""
    actual_qty = serializers.IntegerField(min_value=0)
    condition = serializers.ChoiceField(choices=InventoryCondition.choices)
    remarks = serializers.CharField(required=False, allow_blank=True, max_length=500)


class InventoryItemUpdateSerializer(serializers.Serializer):
    """Serializer for updating inventory records (HM-UC-021)."""
    current_quantity = serializers.IntegerField(min_value=0)
    condition = serializers.ChoiceField(choices=InventoryCondition.choices)
    remarks = serializers.CharField(required=False, allow_blank=True, max_length=500)


class InventoryDiscrepancySerializer(serializers.ModelSerializer):
    """Read-only serializer for reported discrepancies."""
    item_name = serializers.CharField(source='item.name', read_only=True)
    hostel_name = serializers.CharField(source='hostel.name', read_only=True)
    reported_by_name = serializers.CharField(source='reported_by.get_full_name', read_only=True)

    class Meta:
        model = InventoryDiscrepancy
        fields = [
            'id', 'item', 'item_name', 'hostel', 'hostel_name',
            'discrepancy_type', 'expected_qty', 'actual_qty', 'condition',
            'remarks', 'reported_by', 'reported_by_name', 'reported_at'
        ]
        read_only_fields = fields


class ResourceRequestSerializer(serializers.ModelSerializer):
    """Read-only serializer for resource procurement requests."""
    requested_by_name = serializers.CharField(source='requested_by.get_full_name', read_only=True)
    hostel_name = serializers.CharField(source='hostel.name', read_only=True)
    reviewed_by_name = serializers.CharField(source='reviewed_by.get_full_name', read_only=True, allow_null=True)

    class Meta:
        model = ResourceRequest
        fields = [
            'id', 'hostel', 'hostel_name', 'requested_by', 'requested_by_name',
            'request_type', 'category', 'item_name', 'quantity', 'justification',
            'status', 'reviewed_by', 'reviewed_by_name', 'reviewed_at', 'created_at'
        ]
        read_only_fields = fields


class ResourceRequestCreateSerializer(serializers.ModelSerializer):
    """Create serializer for resource requests (HM-UC-022)."""
    class Meta:
        model = ResourceRequest
        fields = ['hostel', 'request_type', 'category', 'item_name', 'quantity', 'justification']

    def validate_quantity(self, value):
        if value <= 0:
            raise serializers.ValidationError("Quantity must be a positive integer (BR-HM-030.b).")
        return value

    def validate(self, data):
        # BR-HM-030.a: BLOCK resource request if any mandatory fields are missing
        # DRF handles presence check for non-nullable fields automatically if required=True
        return data


class ResourceRequestReviewSerializer(serializers.Serializer):
    """Serializer for reviewing a resource request (HM-UC-023)."""
    status = serializers.ChoiceField(choices=[ResourceRequestStatus.APPROVED, ResourceRequestStatus.REJECTED])
    remarks = serializers.CharField(required=False, allow_blank=True, max_length=500)


# ══════════════════════════════════════════════════════════════
# GUEST ROOM SERIALIZERS (HM-WF-112)
# ══════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════
# GUEST ROOM SERIALIZERS (CHUNK 12)
# ══════════════════════════════════════════════════════════════

class GuestRoomPolicySerializer(serializers.ModelSerializer):
    """Serializer for hostel-specific guest booking rules."""
    updated_by_name = serializers.CharField(source='updated_by.get_full_name', read_only=True)
    
    hall_id = serializers.CharField(source='hostel.hall_id', read_only=True)
    
    class Meta:
        model = GuestRoomPolicy
        fields = [
            'id', 'hall_id', 'per_night_rate', 'max_duration_nights',
            'fines_grace_threshold', 'updated_by', 'updated_by_name', 'updated_at'
        ]
        read_only_fields = ['id', 'updated_by', 'updated_at']


class GuestRoomSerializer(serializers.ModelSerializer):
    """Registry serializer (Designating rooms as Guest-Eligible)."""
    room_detail = RoomSerializer(source='room', read_only=True)
    room_number = serializers.CharField(source='room.room_number', read_only=True)
    floor = serializers.IntegerField(source='room.floor', read_only=True)
    hostel_name = serializers.CharField(source='hostel.name', read_only=True)
    is_occupied = serializers.SerializerMethodField()
    
    class Meta:
        model = GuestRoom
        fields = [
            'id', 'hostel', 'hostel_name', 'room', 'room_detail', 'room_number', 'floor',
            'is_active', 'is_occupied', 'created_at'
        ]
        read_only_fields = ['id', 'created_at']

    def get_is_occupied(self, obj):
        return obj.room.current_occupancy > 0


class GuestRoomBookingSerializer(serializers.ModelSerializer):
    """Detailed booking serializer for read operations."""
    student_name = serializers.CharField(source='student.id.user.get_full_name', read_only=True)
    student_roll = serializers.CharField(source='student.id.id', read_only=True)
    room_number = serializers.CharField(source='room.room_number', read_only=True)
    hostel_name = serializers.CharField(source='hostel.name', read_only=True)
    
    class Meta:
        model = GuestRoomBooking
        fields = [
            'id', 'booking_uid', 'student', 'student_name', 'student_roll',
            'hostel', 'hostel_name', 'room', 'room_number',
            'guest_name', 'guest_phone', 'guest_email', 'visit_purpose',
            'check_in_date', 'check_out_date', 'status', 'total_charges',
            'id_proof_type', 'id_proof_number', 'id_verified_at',
            'caretaker_remarks', 'created_at', 'updated_at'
        ]
        read_only_fields = fields


class GuestRoomBookingCreateSerializer(serializers.ModelSerializer):
    """Validation for student booking requests."""
    class Meta:
        model = GuestRoomBooking
        fields = [
            'hostel', 'guest_name', 'guest_phone', 'guest_email', 
            'visit_purpose', 'check_in_date', 'check_out_date',
            'guest_address', 'nationality'
        ]
        extra_kwargs = {
            'hostel': {'required': False}
        }

    def validate_visit_purpose(self, value):
        if not value or len(value.strip()) < 3:
            raise serializers.ValidationError("Purpose of visit must be at least 3 characters.")
        return value

    def validate(self, data):
        if data['check_in_date'] < timezone.now().date():
            raise serializers.ValidationError("Check-in date cannot be in the past.")
        if data['check_out_date'] <= data['check_in_date']:
            raise serializers.ValidationError("Check-out date must be after check-in date.")
        
        duration = (data['check_out_date'] - data['check_in_date']).days
        if duration > 15: # Standard limit
            raise serializers.ValidationError("Booking duration cannot exceed 15 days.")
            
        return data


class GuestRoomCheckInSerializer(serializers.Serializer):
    """Verification for guest check-in."""
    id_proof_type = serializers.CharField(max_length=50)
    id_proof_number = serializers.CharField(max_length=50)


class GuestRoomInspectionSerializer(serializers.ModelSerializer):
    """Output for inspection records."""
    inspected_by_name = serializers.CharField(source='conducted_by.get_full_name', read_only=True)
    condition_remarks = serializers.CharField(source='damage_description', read_only=True)
    damage_severity = serializers.CharField(source='severity', read_only=True)
    damage_charge = serializers.DecimalField(source='estimated_repair_cost', max_digits=10, decimal_places=2, read_only=True)
    inspected_at = serializers.DateTimeField(source='inspection_at', read_only=True)
    
    class Meta:
        model = GuestRoomInspection
        fields = [
            'id', 'booking', 'conducted_by', 'inspected_by_name',
            'condition_remarks', 'damage_severity', 'damage_charge', 'inspected_at'
        ]
        read_only_fields = fields


class GuestRoomCheckOutSerializer(serializers.Serializer):
    """Input for inspection during check-out."""
    from ..models import DamageSeverityChoices
    condition_remarks = serializers.CharField(max_length=500)
    damage_severity = serializers.ChoiceField(choices=DamageSeverityChoices.choices)
    damage_charge = serializers.DecimalField(max_digits=10, decimal_places=2, default=0.00)


# ...existing code...


# ══════════════════════════════════════════════════════════════
# NOTICE BOARD SERIALIZERS (HM-WF-110)
# ══════════════════════════════════════════════════════════════

class NoticeSerializer(serializers.ModelSerializer):
    """
    Refined Notice Serializer (HM-WF-110).
    Enforces Title (5-200) and Description (20-5000) rules.
    """
    hostel_name = serializers.CharField(source='hostel.hall_id', read_only=True)
    created_by_name = serializers.CharField(source='created_by.username', read_only=True)
    is_read = serializers.SerializerMethodField()
    read_count = serializers.SerializerMethodField()

    class Meta:
        model = Notice
        fields = [
            'id', 'notice_uid', 'hostel', 'hostel_name', 'created_by', 'created_by_name',
            'title', 'description', 'priority', 'start_date', 'end_date', 'status',
            'attachment', 'is_read', 'read_count', 'created_at', 'updated_at'
        ]
        read_only_fields = ['id', 'notice_uid', 'created_by', 'created_at', 'updated_at']

    def get_is_read(self, obj):
        request = self.context.get('request')
        if request and request.user.is_authenticated:
            from ..selectors import get_notice_read_status
            return get_notice_read_status(obj.id, request.user)
        return False

    def get_read_count(self, obj):
        from ..selectors import get_notice_read_count
        return get_notice_read_count(obj.id)

    def validate_title(self, value):
        if len(value) < 5 or len(value) > 200:
            raise serializers.ValidationError("Title must be between 5 and 200 characters.")
        return value

    def validate_description(self, value):
        if len(value) < 20 or len(value) > 5000:
            raise serializers.ValidationError("Description must be between 20 and 5000 characters.")
        return value


class NoticeReadStatusSerializer(serializers.ModelSerializer):
    class Meta:
        model = NoticeReadStatus
        fields = '__all__'


class HostelNoticeBoardSerializer(serializers.ModelSerializer):
    """
    LEGACY SERIALIZER - DEPRECATED
    Serializer for Notice Board.
    Enforces:
    - BR-HM-029: Notice Content Validation
    """
    hall_name = serializers.CharField(source='hall.hall_name', read_only=True)
    posted_by_name = serializers.CharField(source='posted_by.username', read_only=True)
    
    class Meta:
        model = HostelNoticeBoard
        fields = [
            'id', 'hall', 'hall_name', 'title', 'description', 'content_file',
            'posted_by', 'posted_by_name', 'is_active', 'posted_date',
            'archive_date', 'updated_at'
        ]
        read_only_fields = ['id', 'posted_by', 'posted_date', 'posted_by_name', 'hall_name']
        
    def validate_title(self, value):
        if not value or len(value) < 5 or len(value) > 200:
            raise serializers.ValidationError("Title must be between 5 and 200 characters.")
        
        profanity = ['spam', 'abuse', 'fake']
        if any(bad_word in value.lower() for bad_word in profanity):
            raise serializers.ValidationError("Title contains prohibited/profane words.")
        return value
        
    def validate_description(self, value):
        if not value or len(value.strip()) < 20:
            raise serializers.ValidationError("Description must be at least 20 characters long.")
            
        profanity = ['spam', 'abuse', 'fake']
        if any(bad_word in value.lower() for bad_word in profanity):
            raise serializers.ValidationError("Description contains prohibited/profane words.")
        return value


# ══════════════════════════════════════════════════════════════
# MISSING APPROVAL SERIALIZERS
# ══════════════════════════════════════════════════════════════


class GuestRoomBookingApprovalSerializer(serializers.Serializer):
    """Serializer for approving/rejecting guest room bookings."""
    decision = serializers.ChoiceField(choices=['approved', 'rejected'])
    remarks = serializers.CharField(required=False, allow_blank=True, max_length=500)
    room_id = serializers.IntegerField(required=False, allow_null=True)



class RoomVacationRequestSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.id.user.username', read_only=True)
    room_number = serializers.CharField(source='room.room_number', read_only=True)
    hall_name = serializers.CharField(source='hall.hall_name', read_only=True)

    class Meta:
        model = RoomVacationRequest
        fields = [
            'id', 'student', 'student_name', 'room', 'room_number', 'hall', 'hall_name',
            'vacation_date', 'status', 'remarks', 'created_at'
        ]
        read_only_fields = ['student', 'status', 'created_at', 'student_name', 'room_number', 'hall_name']


class ExtendedStayApplicationSerializer(serializers.ModelSerializer):
    student_name = serializers.CharField(source='student.id.user.username', read_only=True)
    room_number = serializers.CharField(source='room.room_number', read_only=True)
    hall_name = serializers.CharField(source='hall.hall_name', read_only=True)

    class Meta:
        model = ExtendedStayApplication
        fields = [
            'id', 'student', 'student_name', 'room', 'room_number', 'hall', 'hall_name',
            'start_date', 'end_date', 'reason', 'status', 'remarks', 'created_at'
        ]
        read_only_fields = ['student', 'status', 'created_at', 'student_name', 'room_number', 'hall_name']


# ══════════════════════════════════════════════════════════════
# ATTENDANCE SERIALIZERS
# ══════════════════════════════════════════════════════════════

class StudentAttendanceRecordSerializer(serializers.ModelSerializer):
    """Serializer for modern student attendance records."""
    student_name = serializers.CharField(source='student.id.user.username', read_only=True)
    roll_number = serializers.CharField(source='student.id.id', read_only=True)
    
    class Meta:
        model = StudentAttendanceRecord
        fields = ['id', 'student', 'student_name', 'roll_number', 'date', 'status', 'leave_request']
        read_only_fields = ['id', 'student_name', 'roll_number']


class AttendanceSummarySerializer(serializers.Serializer):
    """Serializer for the caretaker dashboard showing attendance statistics per student."""
    id = serializers.CharField(source='id.id', read_only=True)
    name = serializers.CharField(source='id.user.get_full_name', read_only=True)
    roll_number = serializers.CharField(source='id.id', read_only=True)
    present_count = serializers.IntegerField(read_only=True)
    absent_count = serializers.IntegerField(read_only=True)
    on_leave_count = serializers.IntegerField(read_only=True)


class AbsenceDateSerializer(serializers.ModelSerializer):
    """Simple serializer for listing absence dates."""
    class Meta:
        model = StudentAttendanceRecord
        fields = ['date']
        read_only_fields = fields


    def get_total_rooms(self, obj):
        return obj.rooms_setup.count()


class RoomCapacityDashboardSerializer(serializers.ModelSerializer):
    """High-level summary of hostel capacity for Super Admin."""
    occupied_seats = serializers.SerializerMethodField()
    total_rooms = serializers.SerializerMethodField()
    
    class Meta:
        model = Hostel
        fields = [
            'hall_id', 'name', 'type', 'total_capacity', 
            'occupied_seats', 'total_rooms', 'status'
        ]
        
    def get_occupied_seats(self, obj):
        return obj.allotments.filter(is_active=True).count()
        
    def get_total_rooms(self, obj):
        return obj.rooms_setup.count()


class BulkAllotmentSerializer(serializers.Serializer):
    """Serializer for bulk allotment actions."""
    request_ids = serializers.ListField(
        child=serializers.IntegerField(),
        min_length=1
    )


class BatchAllocationSerializer(serializers.Serializer):
    """
    Serializer for bulk batch allocation by Super Admin.
    Matches students by category, admission year, and gender.
    """
    PROGRAMME_CATEGORIES = [
        ('UG', 'Undergraduate'),
        ('PG', 'Postgraduate'),
        ('M.Tech', 'M.Tech'),
    ]
    GENDER_CHOICES = [
        ('M', 'Male'),
        ('F', 'Female'),
    ]
    
    programme_category = serializers.ChoiceField(choices=PROGRAMME_CATEGORIES)
    admission_year = serializers.IntegerField()
    gender = serializers.ChoiceField(choices=GENDER_CHOICES)

# ══════════════════════════════════════════════════════════════
# SEMESTER END VACATION SERIALIZERS
# ══════════════════════════════════════════════════════════════

class BulkHostelVacationSerializer(serializers.Serializer):
    """Serializer for bulk hostel vacation (empty out)."""
    hostel_ids = serializers.ListField(
        child=serializers.CharField(),
        min_length=1,
        help_text="List of hostel hall_ids to empty out."
    )

    def validate_hostel_ids(self, value):
        valid_hostels = Hostel.objects.filter(hall_id__in=value).values_list('hall_id', flat=True)
        invalid_hostels = set(value) - set(valid_hostels)
        if invalid_hostels:
            raise serializers.ValidationError(f"Invalid hostel IDs: {', '.join(invalid_hostels)}")
        return value


# ══════════════════════════════════════════════════════════════
# SECURITY MANAGEMENT SERIALIZERS (NEW)
# ══════════════════════════════════════════════════════════════

class SecurityGuardSerializer(serializers.ModelSerializer):
    """Serializer for Security Guard profile."""
    class Meta:
        model = SecurityGuard
        fields = ['id', 'user', 'hostel', 'name', 'employee_id', 'contact', 'is_active', 'created_at']
        read_only_fields = ['id', 'created_at']


class GuardShiftSerializer(serializers.ModelSerializer):
    """Serializer for Guard Shift assignments."""
    guard_name = serializers.CharField(source='guard.name', read_only=True)
    hostel_name = serializers.CharField(source='hostel.name', read_only=True)
    assigned_by_name = serializers.CharField(source='assigned_by.username', read_only=True)

    class Meta:
        model = GuardShift
        fields = [
            'id', 'hostel', 'hostel_name', 'guard', 'guard_name', 
            'shift_type', 'start_time', 'end_time', 'date', 
            'assigned_by', 'assigned_by_name', 'is_confirmed', 'created_at'
        ]
        read_only_fields = ['id', 'assigned_by', 'created_at', 'guard_name', 'hostel_name', 'assigned_by_name']


class ShiftScheduleLogSerializer(serializers.ModelSerializer):
    """Read-only serializer for shift audit logs."""
    guard_name = serializers.CharField(source='guard.name', read_only=True)
    hostel_name = serializers.CharField(source='hostel.name', read_only=True)
    performed_by_name = serializers.CharField(source='performed_by.username', read_only=True)

    class Meta:
        model = ShiftScheduleLog
        fields = [
            'id', 'hostel', 'hostel_name', 'guard', 'guard_name', 
            'action', 'performed_by', 'performed_by_name', 'detail_json', 'timestamp'
        ]
        read_only_fields = fields



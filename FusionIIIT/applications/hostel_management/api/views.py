"""
API Views - Thin orchestration layer only.

CRITICAL RULES:
- NO business logic here
- NO database queries (.objects) here
- Only call selectors.py for queries
- Only call services.py for business logic
- Only instantiate serializers
- Keep views extremely thin and readable

Supports Workflows:
- HM-WF-101: Leave Management
- HM-WF-102: Complaint Management
- HM-WF-103: Room Allocation
- HM-WF-104: Room Changes
- HM-WF-105: Fine Management
- HM-WF-107: Staff Scheduling
- HM-WF-108: Inventory
- HM-WF-109: Room Vacation
- HM-WF-110: Notice Board
- HM-WF-112: Guest Room Booking
- HM-WF-113: Extended Stay
"""

from datetime import datetime, timedelta
from django.utils import timezone
from rest_framework import generics, status, parsers
from rest_framework.response import Response
from rest_framework.permissions import IsAuthenticated, IsAdminUser, BasePermission
from rest_framework.pagination import PageNumberPagination
from django.shortcuts import get_object_or_404
from django.db.models import Sum, Count
from django.contrib.auth.models import User
from applications.globals.models import Staff
from applications.globals.models import Faculty
from applications.hostel_management.models import (
    LeaveRequest, StudentAttendanceRecord, AttendanceStatus,
    HostelComplaint,
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
    ComplaintStatusChoices,
    ComplaintCategoryChoices,
    ComplaintPriorityChoices,
    FineStatusChoices,
    AccommodationApplicationWindow,
    AccommodationRequest,
    RoomAllotment,
    Hostel,
    Room,
    HostelTypeChoices,
    RoomTypeChoices,
    StaffRoleChoices,
    HostelStatusChoices,
    HostelStaffAssignment,
    HostelAuditLog,
    ComplaintHistory,
    AllocationChangeStatusChoices, FineCategoryChoices, FineExtraDetail,
    InventoryItem, InventoryDiscrepancy, InventoryAuditLog as InventoryAuditTrail, ResourceRequest,
    InventoryCategory, InventoryCondition, DiscrepancyType, ResourceRequestType, ResourceRequestStatus,
    Notice, NoticeReadStatus, NoticeStatus, NoticePriority,
    BookingStatusChoices, DamageSeverityChoices
)
from . import serializers
from .serializers import (
    LeaveRequestSerializer, LeaveRequestCreateSerializer, LeaveRequestDecisionSerializer,
    HostelComplaintSerializer, HostelComplaintCreateSerializer,
    HostelComplaintResolveSerializer, HostelComplaintEscalateSerializer,
    RoomAllocationChangeSerializer,
    RoomAllocationChangeApprovalSerializer,
    HostelFineSerializer, HostelFinePaymentSerializer, HostelFineWaiverSerializer,
    StaffScheduleSerializer, HostelInventorySerializer,
    GuestRoomBookingSerializer, GuestRoomBookingCreateSerializer, GuestRoomBookingApprovalSerializer,
    HostelNoticeBoardSerializer, NoticeSerializer, NoticeReadStatusSerializer,
    StudentAttendanceRecordSerializer,
    InventoryItemSerializer, InventoryInspectionSerializer, InventoryItemUpdateSerializer,
    InventoryDiscrepancySerializer, InventoryAuditTrailSerializer,
    ResourceRequestSerializer, ResourceRequestCreateSerializer, ResourceRequestReviewSerializer, BulkHostelVacationSerializer
)
from .. import selectors, services
from ..permissions import IsHostelSuperAdmin, IsAssignedToHostel, IsWardenOrAdmin, HasActiveHostelAllotment
from ..services import (
    HostelManagementException, LeaveEligibilityError, LeaveDateError,
    ComplaintEligibilityError, ComplaintRoutingError, ResolutionRemarksError,
    EscalationAuthorizationError, WardenAuthorityError,
    RoomChangeEligibilityError, DualApprovalError, AllotmentCapacityError,
    FineValidationError, ApplicationWindowError
)


# ══════════════════════════════════════════════════════════════
# PAGINATION & ROLE-BASED PERMISSION CLASSES
# ══════════════════════════════════════════════════════════════

class StandardPagination(PageNumberPagination):
    """Standard pagination: 50 items per page for optimized payload."""
    page_size = 50
    page_size_query_param = 'page_size'
    max_page_size = 500
    page_query_param = 'page'


class IsStudent(BasePermission):
    """Permission check: student role."""
    def has_permission(self, request, view):
        return bool(request.user and request.user.is_authenticated and hasattr(request.user, 'student'))


class IsWardenOrCaretaker(BasePermission):
    def has_permission(self, request, view):
        return selectors.is_user_warden_or_caretaker(request.user)


class IsWarden(BasePermission):
    def has_permission(self, request, view):
        return selectors.is_user_warden(request.user)


class IsCaretaker(BasePermission):
    """Permission for Caretaker role only."""
    def has_permission(self, request, view):
        return selectors.is_user_caretaker(request.user)


class IsWardenCaretakerOrAdmin(BasePermission):
    """Combined permission to avoid Bitwise OR issues (DRF < 3.9)."""
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        return (
            request.user.is_superuser or 
            selectors.is_user_warden_or_caretaker(request.user) or
            HasActiveHostelAllotment().has_permission(request, view)
        )


class IsStudent(BasePermission):
    """Permission for Student role."""
    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        from applications.academic_information.models import Student
        return Student.objects.filter(id__user=request.user).exists()


# ══════════════════════════════════════════════════════════════
# FACULTY & STAFF LIST VIEWS
# ══════════════════════════════════════════════════════════════



# ══════════════════════════════════════════════════════════════
# COMPLAINT MANAGEMENT VIEWS (HM-WF-102)
# ══════════════════════════════════════════════════════════════


class FacultyListView(generics.ListAPIView):
    """List all faculty members available for warden assignment."""
    permission_classes = [IsHostelSuperAdmin]
    
    def get(self, request, *args, **kwargs):
        """Get all faculty members."""
        try:
            faculty_list = Faculty.objects.all().select_related('id__user')
            
            faculty_data = []
            for faculty in faculty_list:
                user = faculty.id.user if faculty.id else None
                if user:
                    faculty_data.append({
                        'id': user.id,  # Get the actual User primary key
                        'extra_id': faculty.id.id, # Keep extra_id for reference
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'email': user.email,
                    })
            
            return Response(faculty_data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class StaffListView(generics.ListAPIView):
    """List all staff members available for caretaker assignment."""
    permission_classes = [IsHostelSuperAdmin]
    
    def get(self, request, *args, **kwargs):
        """Get all staff members."""
        try:
            staff_list = Staff.objects.all().select_related('id__user')
            
            staff_data = []
            for staff_member in staff_list:
                user = staff_member.id.user if staff_member.id else None
                if user:
                    staff_data.append({
                        'id': user.id,  # Get the actual User primary key
                        'extra_id': staff_member.id.id, # Keep extra_id for reference
                        'first_name': user.first_name,
                        'last_name': user.last_name,
                        'email': user.email,
                    })
            
            return Response(staff_data, status=status.HTTP_200_OK)
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


class ListRoomsByHostelView(generics.ListAPIView):
    """
    List all rooms for a specific hostel.
    GET /api/hostel/halls/<hall_id>/rooms/
    """
    permission_classes = [IsAuthenticated]
    serializer_class = serializers.RoomSerializer

    def get_queryset(self):
        hostel_id = self.kwargs.get('pk')
        return selectors.list_rooms_by_hostel(hostel_id)


class RoomRenameView(generics.UpdateAPIView):
    """Rename a room (Warden/Caretaker can rename rooms from sequential to custom names)."""
    permission_classes = [IsWardenOrCaretaker]
    serializer_class = serializers.RoomSetupSerializer

    def get_object(self):
        """Get room by ID."""
        room_id = self.kwargs['pk']
        return get_object_or_404(Room, pk=room_id)

    def patch(self, request, *args, **kwargs):
        """
        Rename room.
        Request body: { "room_number": "A101", "floor": 1 }
        """
        try:
            room_id = self.kwargs['pk']
            room = get_object_or_404(Room, pk=room_id)
            room_number = request.data.get('room_number')
            floor = request.data.get('floor')
            
            if not room_number:
                return Response(
                    {'error': 'room_number is required'},
                    status=status.HTTP_400_BAD_REQUEST
                )
            
            updated_room = services.rename_room_in_hostel(room, room_number, floor)
            
            return Response(
                {'message': 'Room renamed successfully'},
                status=status.HTTP_200_OK
            )
        except Exception as e:
            return Response(
                {'error': str(e)},
                status=status.HTTP_400_BAD_REQUEST
            )


# ══════════════════════════════════════════════════════════════
# LEAVE MANAGEMENT VIEWS (HM-WF-101)
# ══════════════════════════════════════════════════════════════

class LeaveListCreateView(generics.ListCreateAPIView):
    """List leaves or submit a new leave request (BR-HM-101 to 103)."""
    permission_classes = [IsAuthenticated, HasActiveHostelAllotment]
    parser_classes = (parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser)
    
    def get_queryset(self):
        """Get leaves for authenticated student or all leaves for authorized staff."""
        user = self.request.user
        if selectors.is_user_warden_or_caretaker(user) or user.is_superuser:
            return selectors.get_all_leaves()
        return selectors.get_student_leaves(user)

    def get_serializer_class(self):
        """Use writable serializer for POST (enforces BR-HM-103), read-only for GET."""
        if self.request.method == 'POST':
            return LeaveRequestCreateSerializer
        return LeaveRequestSerializer

    def perform_create(self, serializer):
        """Submit leave request via service with mandatory residency and document checks."""
        try:
            student = selectors.get_student(self.request.user)
            if not student:
                raise HostelManagementException("Only students can submit leave requests.")

            services.create_leave_request(
                student=student,
                start_date=serializer.validated_data['start_date'],
                end_date=serializer.validated_data['end_date'],
                reason=serializer.validated_data['reason'],
                documents=self.request.FILES.get('documents') or serializer.validated_data.get('documents')
            )
        except (LeaveEligibilityError, LeaveDateError, HostelManagementException) as e:
            from rest_framework.exceptions import ValidationError
            print(f"DEBUG: Leave creation failed logic check: {str(e)}")
            raise ValidationError({"detail": str(e)})

    def post(self, request, *args, **kwargs):
        """Override post to debug validation errors."""
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            print(f"DEBUG: Serializer Errors: {serializer.errors}")
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)
        return super().post(request, *args, **kwargs)


class LeaveMyListView(generics.ListAPIView):
    """List only the authenticated user's leave requests."""
    permission_classes = [IsAuthenticated]
    serializer_class = LeaveRequestSerializer

    def get_queryset(self):
        return selectors.get_student_leaves(self.request.user)


class LeaveRetrieveUpdateView(generics.RetrieveUpdateAPIView):
    """Retrieve or update leave request details."""
    permission_classes = [IsAuthenticated]
    serializer_class = LeaveRequestSerializer

    def get_object(self):
        """Get leave request by ID."""
        return get_object_or_404(LeaveRequest, pk=self.kwargs['pk'])


class LeaveApproveView(generics.UpdateAPIView):
    """Approve a leave request (BR-HM-104, BR-HM-105)."""
    permission_classes = [IsAuthenticated, IsWardenOrCaretaker]
    serializer_class = LeaveRequestDecisionSerializer

    def post(self, request, *args, **kwargs):
        """Debug post for approval."""
        print(f"DEBUG: LeaveApprove Attempt by {request.user} for ID {self.kwargs.get('pk')}")
        return self.patch(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        """Debug patch for approval."""
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            print(f"DEBUG: LeaveApprove Serializer Errors: {serializer.errors}")
        return super().patch(request, *args, **kwargs)

    def get_object(self):
        """Get leave request by ID."""
        return get_object_or_404(LeaveRequest, pk=self.kwargs['pk'])

    def perform_update(self, serializer):
        """Approve leave via service with atomic attendance sync."""
        leave = self.get_object()
        services.approve_leave(
            leave_id=leave.id,
            decided_by=self.request.user,
            remarks=serializer.validated_data.get('decision_remarks')
        )


class LeaveRejectView(generics.UpdateAPIView):
    """Reject a leave request."""
    permission_classes = [IsAuthenticated]
    serializer_class = LeaveRequestDecisionSerializer

    def post(self, request, *args, **kwargs):
        return self.patch(request, *args, **kwargs)

    def patch(self, request, *args, **kwargs):
        return super().patch(request, *args, **kwargs)

    def get_object(self):
        return get_object_or_404(LeaveRequest, pk=self.kwargs['pk'])

    def perform_update(self, serializer):
        leave = self.get_object()
        services.reject_leave(
            leave_id=leave.id,
            decided_by=self.request.user,
            rejection_reason=serializer.validated_data.get('decision_remarks')
        )


# ══════════════════════════════════════════════════════════════
# COMPLAINT MANAGEMENT VIEWS (HM-WF-102)
# ══════════════════════════════════════════════════════════════

class ComplaintListCreateView(generics.ListCreateAPIView):
    """List complaints (scoped) or submit new."""
    permission_classes = [IsAuthenticated, HasActiveHostelAllotment]
    parser_classes = [parsers.MultiPartParser, parsers.FormParser, parsers.JSONParser]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return HostelComplaintCreateSerializer
        return HostelComplaintSerializer

    def get_queryset(self):
        user = self.request.user
        if user.is_superuser:
            return HostelComplaint.objects.all()
        
        student = selectors.get_student(user)
        if student:
            return selectors.list_student_complaints(student)

        if selectors.is_user_warden(user):
            assignments = selectors.list_user_staff_assignments(user, role=StaffRoleChoices.WARDEN)
            hostel_ids = [a.hostel.hall_id for a in assignments]
            return HostelComplaint.objects.filter(hostel__hall_id__in=hostel_ids)
        
        if selectors.is_user_caretaker(user):
            assignments = selectors.list_user_staff_assignments(user, role=StaffRoleChoices.CARETAKER)
            hostel_ids = [a.hostel.hall_id for a in assignments]
            return HostelComplaint.objects.filter(hostel__hall_id__in=hostel_ids).exclude(category=ComplaintCategoryChoices.SECURITY)

        return HostelComplaint.objects.none()

    def perform_create(self, serializer):
        student = selectors.get_student(self.request.user)
        if not student:
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only students can submit.")
        try:
            services.create_complaint(
                student=student,
                category=serializer.validated_data['category'],
                description=serializer.validated_data['description'],
                attachments=self.request.FILES.get('attachments')
            )
        except Exception as e:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': str(e)})


class ComplaintDetailView(generics.RetrieveAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = HostelComplaintSerializer
    queryset = HostelComplaint.objects.all()


class StartComplaintView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    def post(self, request, pk):
        try:
            complaint = services.update_complaint_to_in_progress(pk, request.user)
            return Response(HostelComplaintSerializer(complaint).data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)


class EscalateComplaintView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = HostelComplaintEscalateSerializer
    def post(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            complaint = services.escalate_complaint(pk, request.user, serializer.validated_data['reason'])
            return Response(HostelComplaintSerializer(complaint).data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)


class ResolveComplaintView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    serializer_class = HostelComplaintResolveSerializer
    def post(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        try:
            complaint = services.resolve_complaint(pk, request.user, serializer.validated_data['resolution_remarks'])
            return Response(HostelComplaintSerializer(complaint).data)
        except Exception as e:
            return Response({'detail': str(e)}, status=400)


class ComplaintReportView(generics.GenericAPIView):
    permission_classes = [IsAuthenticated]
    def get(self, request):
        if not selectors.is_user_warden(request.user):
            from rest_framework.exceptions import PermissionDenied
            raise PermissionDenied("Only Wardens can view reports.")
        from django.db.models import Count
        metrics = HostelComplaint.objects.values('category', 'status').annotate(total=Count('id'))
        return Response({
            'metrics': metrics,
            'summary': {
                'total_complaints': HostelComplaint.objects.count(),
                'resolved_today': HostelComplaint.objects.filter(status=ComplaintStatusChoices.RESOLVED, resolved_at__date=timezone.now().date()).count()
            }
        })


# ══════════════════════════════════════════════════════════════
# HM-WF-103: ACCOMMODATION REQUEST & ALLOTMENT VIEWS
# ══════════════════════════════════════════════════════════════

class ListWindowsView(generics.ListAPIView):
    """List all accommodation application windows."""
    permission_classes = [IsAuthenticated]
    serializer_class = serializers.AccommodationApplicationWindowSerializer
    queryset = selectors.list_all_application_windows()


class SubmitAccommodationRequestView(generics.CreateAPIView):
    """Submit a new accommodation request (Student only)."""
    permission_classes = [IsStudent]
    serializer_class = serializers.AccommodationRequestSerializer

    def perform_create(self, serializer):
        try:
            student = getattr(self.request.user, 'student', None)
            if not student:
                raise HostelManagementException("User profile not found.")

            services.create_accommodation_request(
                student=student,
                window_id=self.request.data.get('window'),
                preferred_hostel_type=self.request.data.get('preferred_hostel_type'),
                preferred_room_type=self.request.data.get('preferred_room_type')
            )
        except ApplicationWindowError as e:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': str(e)})


class ListRequestsView(generics.ListAPIView):
    """List all pending accommodation requests."""
    permission_classes = [IsHostelSuperAdmin | IsWardenOrCaretaker]
    serializer_class = serializers.AccommodationRequestSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        window_id = self.request.query_params.get('window_id')
        return selectors.list_pending_requests(window_id)


class RoomCapacityDashboardView(generics.ListAPIView):
    """View hostel capacity and occupancy dashboard."""
    permission_classes = [IsHostelSuperAdmin | IsWardenOrCaretaker]
    serializer_class = serializers.RoomCapacityDashboardSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = Hostel.objects.prefetch_related('rooms_setup')
        
        if user.is_superuser:
            return queryset.all()
        
        # Filter for Warden/Caretaker assigned hostels
        assigned_query = selectors.list_assigned_hostels(user)
        return queryset.filter(hall_id__in=assigned_query.values_list('hall_id', flat=True))


class MyAllotmentView(generics.RetrieveAPIView):
    """View the active allotment for the current authenticated student."""
    permission_classes = [IsAuthenticated, HasActiveHostelAllotment]
    serializer_class = serializers.RoomAllotmentSerializer

    def get_object(self):
        # Use same pattern as selectors.get_student for 100% consistency
        student = selectors.get_student(self.request.user)
        if not student:
            return None
        
        allotment = selectors.get_active_allotment_by_student(student)
        if not allotment:
            # We raise a standard DRF NotFound to avoid ambiguity with generic 404s
            from rest_framework.exceptions import NotFound
            raise NotFound("No active or legacy allotment found for current student.")
        
        return allotment


class BulkAllotmentView(generics.GenericAPIView):
    """Perform bulk allotment for selected requests."""
    permission_classes = [IsHostelSuperAdmin | IsWardenOrCaretaker]
    serializer_class = serializers.BulkAllotmentSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        request_ids = serializer.validated_data.get('request_ids')
        results = services.perform_bulk_allotment_logic(
            request_ids=request_ids,
            allotted_by=request.user
        )
        
        return Response(results, status=status.HTTP_200_OK)


class BulkBatchAllocationView(generics.GenericAPIView):
    """
    Perform bulk batch allocation for a hostel.
    Allocates students sequentially by floor and room number.
    """
    permission_classes = [IsHostelSuperAdmin | IsWardenOrCaretaker]
    serializer_class = serializers.BatchAllocationSerializer

    def post(self, request, pk, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            results = services.perform_bulk_batch_allocation(
                hall_id=pk,
                programme_category=serializer.validated_data.get('programme_category'),
                admission_year=serializer.validated_data.get('admission_year'),
                gender=serializer.validated_data.get('gender'),
                allotted_by=request.user
            )
            return Response(results, status=status.HTTP_200_OK)
        except ValueError as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)
        except Exception as e:
            return Response({'error': f'An unexpected error occurred during allocation: {str(e)}'}, 
                            status=status.HTTP_500_INTERNAL_SERVER_ERROR)



class RoomAllotmentListView(generics.ListAPIView):
    """
    Administrative list of room allotments.
    - SuperAdmin: View all (can filter by hall)
    - Warden/Caretaker: View only for their assigned halls
    - Chunks: StandardPagination (50 per page)
    """
    serializer_class = serializers.RoomAllotmentSerializer
    pagination_class = StandardPagination
    
    def get_permissions(self):
        # Accessible by SuperAdmin, Warden, or Caretaker
        return [IsAuthenticated(), (IsHostelSuperAdmin | IsWardenOrCaretaker)()]

    def get_queryset(self):
        user = self.request.user
        hall_id = self.request.query_params.get('hall') # Hall filter (actually hostel.hall_id)

        if user.is_superuser:
            # Show all for Super Admin
            return selectors.list_active_room_allotments(hall_id=hall_id)
        
        # Determine accessible hostels for Warden/Caretaker using robust selector
        assigned_hostels = selectors.list_assigned_hostels(user)
        assigned_hall_ids = list(assigned_hostels.values_list('hall_id', flat=True))

        if not assigned_hall_ids:
            return RoomAllotment.objects.none()

        # If hall filter provided, ensure it's within assigned hostels
        if hall_id and hall_id in assigned_hall_ids:
            return selectors.list_active_room_allotments(hall_id=hall_id)
        
        # Return all allotments in assigned hostels, ordered by room number
        return RoomAllotment.objects.filter(
            hostel_id__in=assigned_hall_ids,
            is_active=True
        ).select_related('student__id__user', 'room', 'hostel').order_by('room__room_number')


class RoomAllotmentDestroyView(generics.DestroyAPIView):
    """
    Permanently delete a room allotment (SuperAdmin only).
    - Reconciles room occupancy via service.
    """
    queryset = RoomAllotment.objects.all()
    permission_classes = [IsHostelSuperAdmin]

    def perform_destroy(self, instance):
        """Call service to handle deletion with occupancy logic."""
        try:
            services.delete_room_allotment(instance.id)
        except HostelManagementException as e:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"detail": str(e)})
        except Exception as e:
            from rest_framework.exceptions import APIException
            import traceback
            # Log the full traceback to the server console for the user to see
            print(traceback.format_exc())
            # Re-raise as APIException but with 400 to avoid generic 500 in Axios
            exc = APIException(detail=f"Unexpected deletion error: {str(e)}")
            exc.status_code = 400
            raise exc


# ══════════════════════════════════════════════════════════════
# ROOM CHANGE VIEWS (HM-WF-104)
# ══════════════════════════════════════════════════════════════

class RoomChangeListCreateView(generics.ListCreateAPIView):
    """List room changes or request a room change."""
    permission_classes = [IsAuthenticated, HasActiveHostelAllotment]
    serializer_class = RoomAllocationChangeSerializer

    def get_queryset(self):
        """Get room changes for user or all if staff/warden/caretaker."""
        user = self.request.user
        if user.is_staff or user.is_superuser or selectors.is_user_warden_or_caretaker(user):
            return selectors.get_all_room_changes()
        return selectors.get_student_room_changes(user)

    def perform_create(self, serializer):
        """Request room change via service.
        
        Auto-detects the student's current room from their active allotment.
        The frontend only needs to send: requested_room (ID) and reason.
        """
        try:
            # Resolve Student object from User
            student = selectors.get_student(self.request.user.id)
            if not student:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"detail": "Only students can request room changes."})

            # Auto-detect current room from active allotment
            current_allotment = selectors.get_active_allotment_by_student(student)
            if not current_allotment or not current_allotment.room:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"detail": "You must have an active room allotment to request a room change."})

            current_room = current_allotment.room

            # Get requested_room from serializer data
            requested_room = serializer.validated_data.get('requested_room')
            if not requested_room:
                from rest_framework.exceptions import ValidationError
                raise ValidationError({"detail": "Please select a room to move to."})

            services.request_room_change(
                student=student,
                current_room=current_room,
                requested_room=requested_room,
                reason=serializer.validated_data['reason']
            )
        except (RoomChangeEligibilityError, HostelManagementException) as e:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"detail": str(e)})


class RoomChangeRetrieveView(generics.RetrieveAPIView):
    """Retrieve room change request details."""
    permission_classes = [IsAuthenticated]
    serializer_class = RoomAllocationChangeSerializer

    def get_object(self):
        """Get room change by ID."""
        return get_object_or_404(RoomAllocationChange, pk=self.kwargs['pk'])


class RoomChangeApproveView(generics.UpdateAPIView):
    """Approve a room change request."""
    permission_classes = [IsAuthenticated]
    serializer_class = RoomAllocationChangeApprovalSerializer

    def get_object(self):
        """Get room change by ID."""
        return get_object_or_404(RoomAllocationChange, pk=self.kwargs['pk'])

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({"detail": "Room change approved successfully."}, status=status.HTTP_200_OK)

    def perform_update(self, serializer):
        """Approve room change via service."""
        room_change = self.get_object()
        try:
            services.approve_room_change(
                change_id=room_change.id,
                approved_by=self.request.user,
                remarks=serializer.validated_data.get('remarks')
            )
        except (RoomChangeEligibilityError, DualApprovalError, AllotmentCapacityError, HostelManagementException) as e:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"detail": str(e)})


class RoomChangeRejectView(generics.UpdateAPIView):
    """Reject a room change request."""
    permission_classes = [IsAuthenticated]
    serializer_class = RoomAllocationChangeApprovalSerializer

    def get_object(self):
        """Get room change by ID."""
        return get_object_or_404(RoomAllocationChange, pk=self.kwargs['pk'])

    def update(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        self.perform_update(serializer)
        return Response({"detail": "Room change rejected successfully."}, status=status.HTTP_200_OK)

    def perform_update(self, serializer):
        """Reject room change via service."""
        room_change = self.get_object()
        rejection_reason = serializer.validated_data.get('remarks', '')
        try:
            services.reject_room_change(
                change_id=room_change.id,
                rejection_reason=rejection_reason
            )
        except HostelManagementException as e:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"detail": str(e)})


# ══════════════════════════════════════════════════════════════
# FINE MANAGEMENT VIEWS (HM-WF-105)
# ══════════════════════════════════════════════════════════════

class FineListCreateView(generics.ListCreateAPIView):
    """
    List fines or impose a new fine.
    - Student: view own
    - Caretaker: view assigned hostel
    - Warden: view assigned hostel
    - Admin: view all
    """
    permission_classes = [IsAuthenticated, HasActiveHostelAllotment]
    
    def get_serializer_class(self):
        if self.request.method == 'POST':
            return serializers.ImposeFineSerializer
        return serializers.HostelFineSerializer

    def get_queryset(self):
        """Implement role-based scoping (BR-HM-012)."""
        user = self.request.user
        
        # Super Admin
        if user.is_superuser:
            return selectors.list_hostel_fines()
            
        # Warden/Caretaker
        if selectors.is_user_warden_or_caretaker(user):
            assigned_hostels = selectors.list_assigned_hostels(user)
            hall_ids = assigned_hostels.values_list('hall_id', flat=True)
            return selectors.list_hostel_fines(hall_ids=hall_ids)
            
        # Student
        return selectors.list_student_fines(user)

    def perform_create(self, serializer):
        """Impose fine via service (HM-UC-016)."""
        # Validate student exists
        student_id = serializer.validated_data['student_id']
        student = selectors.get_student_by_roll(student_id)
        if not student:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"student_id": f"Student with ID {student_id} not found."})

        # Validate Caretaker is assigned to this student's hostel
        # BR-HM: Caretaker can only impose fines in their ASSIGNED hostel
        # Get active allotment to find student's hostel
        allotment = selectors.get_active_allotment_by_student(student)
        if not allotment:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"detail": "Student is not currently allotted to any hostel."})
            
        hostel = allotment.hostel
        user = self.request.user
        
        if not user.is_superuser:
            assigned_hostels = selectors.list_assigned_hostels(user)
            if not assigned_hostels.filter(hall_id=hostel.hall_id).exists():
                from rest_framework.exceptions import PermissionDenied
                raise PermissionDenied("You can only impose fines on students in your assigned hostel.")

        try:
            services.impose_fine(
                student=student,
                hostel=hostel,
                imposed_by=user,
                category=serializer.validated_data['category'],
                amount=serializer.validated_data['amount'],
                reason=serializer.validated_data['reason'],
                evidence=serializer.validated_data.get('evidence'),
                extra_details=serializer.validated_data.get('extra_fields')
            )
        except services.FineValidationError as e:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({"detail": str(e)})


class RepeatOffendersView(generics.ListAPIView):
    """
    Warden analytical view to identify repeat offenders.
    Supports in-UI threshold adjustment.
    """
    permission_classes = [IsWardenOrCaretaker | IsHostelSuperAdmin]
    serializer_class = serializers.StudentMinimalSerializer # Need to create or use existing

    def get_queryset(self):
        user = self.request.user
        threshold = self.request.query_params.get('threshold', 3)
        try:
            threshold = int(threshold)
        except ValueError:
            threshold = 3
            
        hall_ids = None
        if not user.is_superuser:
            assigned_hostels = selectors.list_assigned_hostels(user)
            hall_ids = assigned_hostels.values_list('hall_id', flat=True)
            
        return selectors.list_repeat_offenders(hall_ids=hall_ids, threshold=threshold)

    def list(self, request, *args, **kwargs):
        queryset = self.get_queryset()
        # Return custom data including counts
        data = [{
            'id': s.id.id,
            'name': s.id.user.get_full_name(),
            'unpaid_count': s.unpaid_count,
            'total_unpaid_amount': s.total_unpaid_amount,
            'hostel': s.room_allotments.filter(is_active=True).first().hostel.name if s.room_allotments.filter(is_active=True).exists() else "N/A"
        } for s in queryset]
        return Response(data)


class FineReportView(generics.GenericAPIView):
    """
    Warden dashboard statistics and trends for fines.
    """
    permission_classes = [IsWardenOrCaretaker | IsHostelSuperAdmin]

    def get_hall_ids(self, user):
        if user.is_superuser:
            return None
        assigned_hostels = selectors.list_assigned_hostels(user)
        return assigned_hostels.values_list('hall_id', flat=True)

    def get(self, request, *args, **kwargs):
        user = request.user
        hall_ids = self.get_hall_ids(user)
        report_data = selectors.get_fine_report_data(hall_ids=hall_ids)
        return Response(report_data)


class StudentDetailByRollView(generics.GenericAPIView):
    """Fetch student detail by roll number (for auto-fetch features)."""
    permission_classes = [IsWardenOrCaretaker | IsHostelSuperAdmin]

    def get(self, request, roll_number, *args, **kwargs):
        student = selectors.get_student_by_roll(roll_number)
        if not student:
            return Response({"error": "Student not found"}, status=status.HTTP_404_NOT_FOUND)
            
        return Response({
            "name": f"{student.id.user.first_name} {student.id.user.last_name}",
            "roll_number": student.id.id,
            "hostel": student.room_allotments.filter(is_active=True).first().hostel.name if student.room_allotments.filter(is_active=True).exists() else "N/A"
        })


class FineRetrieveView(generics.RetrieveAPIView):
    """Retrieve fine details."""
    permission_classes = [IsAuthenticated]
    serializer_class = HostelFineSerializer

    def get_object(self):
        """Get fine by ID."""
        return get_object_or_404(HostelFine, pk=self.kwargs['pk'])


class FineMarkPaidView(generics.GenericAPIView):
    """Mark fine as paid (HM-UC-017)."""
    permission_classes = [IsWardenOrCaretaker | IsHostelSuperAdmin]
    
    def post(self, request, pk, *args, **kwargs):
        try:
            fine = services.mark_fine_as_paid(fine_id=pk, user=request.user)
            return Response(serializers.HostelFineSerializer(fine).data, status=status.HTTP_200_OK)
        except HostelManagementException as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class FineWaiveView(generics.UpdateAPIView):
    """Waive a fine."""
    permission_classes = [IsAuthenticated]
    serializer_class = HostelFineWaiverSerializer

    def get_object(self):
        """Get fine by ID."""
        return get_object_or_404(HostelFine, pk=self.kwargs['pk'])

    def perform_update(self, serializer):
        """Waive fine via service."""
        fine = self.get_object()
        services.waive_fine(
            fine_id=fine.id,
            waived_by=self.request.user,
            reason=serializer.validated_data.get('waive_reason', '')
        )


# ══════════════════════════════════════════════════════════════
# STAFF SCHEDULE VIEWS (HM-WF-107)
# ══════════════════════════════════════════════════════════════

class StaffScheduleListCreateView(generics.ListCreateAPIView):
    """List schedules or create a new schedule."""
    permission_classes = [IsAuthenticated]
    serializer_class = StaffScheduleSerializer

    def get_queryset(self):
        """Get all staff schedules."""
        return selectors.get_all_schedules()

    def perform_create(self, serializer):
        """Create schedule via service."""
        services.create_staff_schedule(
            hall_id=serializer.validated_data['hall'].id,
            staff_id=serializer.validated_data['staff'].id,
            day_of_week=serializer.validated_data['day_of_week'],
            start_time=serializer.validated_data['start_time'],
            end_time=serializer.validated_data['end_time'],
            shift_type=serializer.validated_data.get('shift_type')
        )


class StaffScheduleRetrieveUpdateDestroyView(generics.RetrieveUpdateDestroyAPIView):
    """Retrieve, update, or delete a schedule."""
    permission_classes = [IsAuthenticated]
    serializer_class = StaffScheduleSerializer

    def get_object(self):
        """Get schedule by ID."""
        return get_object_or_404(StaffSchedule, pk=self.kwargs['pk'])


# ══════════════════════════════════════════════════════════════
# INVENTORY MANAGEMENT VIEWS (HM-WF-108)
# ══════════════════════════════════════════════════════════════

class InventoryListCreateView(generics.ListCreateAPIView):
    """List inventory items or add a new item."""
    permission_classes = [IsAuthenticated]
    serializer_class = HostelInventorySerializer

    def get_queryset(self):
        """Get all inventory items."""
        return selectors.get_all_inventory()

    def perform_create(self, serializer):
        """Add legacy inventory item via service."""
        services.add_inventory_item(
            hall_id=serializer.validated_data['hostel'].id,
            item_name=serializer.validated_data['item_name'],
            quantity=serializer.validated_data['quantity'],
            unit_cost=serializer.validated_data['unit_cost'],
            remarks=serializer.validated_data.get('remarks')
        )


# ══════════════════════════════════════════════════════════════
# MODERN INVENTORY VIEWS (HM-WF-108)
# ══════════════════════════════════════════════════════════════
from rest_framework import viewsets
from rest_framework.decorators import action

class InventoryItemViewSet(viewsets.ModelViewSet):
    """
    ViewSet for Inventory Items.
    - HM-UC-020: Record Inspection
    - HM-UC-021: Update Record
    """
    permission_classes = [IsAuthenticated, IsWardenCaretakerOrAdmin]
    serializer_class = InventoryItemSerializer

    def get_queryset(self):
        return selectors.list_inventory_items(self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsCaretaker])
    def inspect(self, request, pk=None):
        """Record an inspection for a specific item."""
        serializer = InventoryInspectionSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            item = services.record_inventory_inspection(
                item_id=pk,
                actual_qty=serializer.validated_data['actual_qty'],
                condition=serializer.validated_data['condition'],
                performer=request.user,
                remarks=serializer.validated_data.get('remarks', "")
            )
            return Response(InventoryItemSerializer(item).data)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsWardenCaretakerOrAdmin])
    def update_record(self, request, pk=None):
        """Update inventory quantity/condition directly."""
        serializer = InventoryItemUpdateSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            item = services.update_inventory_record(
                item_id=pk,
                quantity=serializer.validated_data['current_quantity'],
                condition=serializer.validated_data['condition'],
                performer=request.user,
                remarks=serializer.validated_data['remarks']
            )
            return Response(InventoryItemSerializer(item).data)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)

    @action(detail=False, methods=['post'], url_path='bulk-upload', permission_classes=[IsAuthenticated, IsWardenCaretakerOrAdmin])
    def bulk_upload(self, request):
        """Bulk upload inventory from Excel."""
        hostel_id = request.data.get('hostel_id')
        excel_file = request.FILES.get('file')

        if not hostel_id or not excel_file:
            return Response({'detail': 'hostel_id and file are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            results = services.bulk_upload_inventory(
                hostel_id=hostel_id,
                excel_file=excel_file,
                user=request.user
            )
            return Response(results)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class InventoryDiscrepancyViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing inventory discrepancies."""
    permission_classes = [IsAuthenticated, IsWardenCaretakerOrAdmin]
    serializer_class = InventoryDiscrepancySerializer

    def get_queryset(self):
        return selectors.list_discrepancies(self.request.user)

    @action(detail=True, methods=['post'], permission_classes=[IsAuthenticated, IsWardenOrAdmin])
    def resolve(self, request, pk=None):
        """Resolve discrepancy by syncing inventory."""
        try:
            item = services.resolve_discrepancy(discrepancy_id=pk, user=request.user)
            return Response(InventoryItemSerializer(item).data)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class InventoryAuditTrailViewSet(viewsets.ReadOnlyModelViewSet):
    """ViewSet for viewing immutable inventory audit trails."""
    permission_classes = [IsAuthenticated, IsWardenCaretakerOrAdmin]
    serializer_class = InventoryAuditTrailSerializer

    def get_queryset(self):
        item_id = self.request.query_params.get('item_id')
        return selectors.list_inventory_audit_logs(self.request.user, item_id=item_id)


class ResourceRequestViewSet(viewsets.ModelViewSet):
    """
    ViewSet for resource procurement requests.
    - HM-UC-022: Submit Request
    - HM-UC-023: Review Request (Admin only)
    """
    permission_classes = [IsAuthenticated]

    def get_serializer_class(self):
        if self.action == 'create':
            return ResourceRequestCreateSerializer
        return ResourceRequestSerializer

    def get_queryset(self):
        return selectors.list_resource_requests(self.request.user)

    def get_permissions(self):
        if self.action == 'create':
            return [IsAuthenticated(), IsCaretaker()]
        return [IsAuthenticated(), IsWardenCaretakerOrAdmin()]

    def perform_create(self, serializer):
        try:
            services.submit_resource_request(
                hostel_id=serializer.validated_data['hostel'].hall_id,
                requester=self.request.user,
                request_type=serializer.validated_data['request_type'],
                category=serializer.validated_data['category'],
                item_name=serializer.validated_data['item_name'],
                quantity=serializer.validated_data['quantity'],
                justification=serializer.validated_data['justification']
            )
        except Exception as e:
            from rest_framework.exceptions import ValidationError
            raise ValidationError({'detail': str(e)})

    @action(detail=True, methods=['post'], permission_classes=[IsWardenOrAdmin])
    def review(self, request, pk=None):
        """Approve or reject a resource request (Admin only)."""
        serializer = ResourceRequestReviewSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            res_request = services.review_resource_request(
                request_id=pk,
                reviewer=request.user,
                status=serializer.validated_data['status'],
                remarks=serializer.validated_data.get('remarks', "")
            )
            return Response(ResourceRequestSerializer(res_request).data)
        except Exception as e:
            return Response({'detail': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class InventoryRetrieveUpdateView(generics.RetrieveUpdateAPIView):
    """Retrieve or update inventory item."""
    permission_classes = [IsAuthenticated]
    serializer_class = HostelInventorySerializer

    def get_object(self):
        """Get inventory by ID."""
        return get_object_or_404(HostelInventory, pk=self.kwargs['pk'])

    def perform_update(self, serializer):
        """Update inventory via service."""
        inventory = self.get_object()
        services.update_inventory(
            inventory_id=inventory.id,
            quantity=serializer.validated_data.get('quantity'),
            remarks=serializer.validated_data.get('remarks')
        )


# ...existing code...


# ══════════════════════════════════════════════════════════════
# GUEST ROOM BOOKING VIEWS (HM-WF-112)
# ══════════════════════════════════════════════════════════════

# ══════════════════════════════════════════════════════════════
# GUEST ROOM MANAGEMENT VIEWS (CHUNK 12)
# ══════════════════════════════════════════════════════════════

class GuestRoomPolicyView(generics.GenericAPIView):
    """Manage hostel-specific guest room policies."""
    permission_classes = [IsWardenOrCaretaker | IsHostelSuperAdmin]
    serializer_class = serializers.GuestRoomPolicySerializer

    def get(self, request, hall_id):
        policy = selectors.get_guest_policy(hall_id)
        if not policy:
            return Response({"detail": "Policy not found for this hostel."}, status=404)
        return Response(self.get_serializer(policy).data)

    def post(self, request, hall_id):
        hostel = get_object_or_404(Hostel, hall_id=hall_id)
        # Check permission for this specific hostel
        if not (request.user.is_superuser or selectors.list_assigned_hostels(request.user).filter(hall_id=hall_id).exists()):
             return Response({"detail": "Not authorized for this hostel."}, status=403)
             
        policy = services.update_guest_policy_service(
            hostel=hostel,
            caretaker_user=request.user,
            **request.data
        )
        return Response(self.get_serializer(policy).data)

    def delete(self, request, hall_id):
        hostel = get_object_or_404(Hostel, hall_id=hall_id)
        if not (request.user.is_superuser or selectors.list_assigned_hostels(request.user).filter(hall_id=hall_id).exists()):
             return Response({"detail": "Not authorized for this hostel."}, status=403)
             
        policy = selectors.get_guest_policy(hall_id)
        if policy:
            policy.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class GuestRoomRegistryViewSet(viewsets.ModelViewSet):
    """Manage designating rooms as Guest-Eligible."""
    permission_classes = [IsWardenOrCaretaker | IsHostelSuperAdmin]
    serializer_class = serializers.GuestRoomSerializer

    def get_queryset(self):
        hall_id = self.request.query_params.get('hall_id')
        return selectors.list_guest_rooms_registry(hall_id)

    def create(self, request, *args, **kwargs):
        room_id = request.data.get('room')
        room = get_object_or_404(Room, id=room_id)
        
        # Check permission for the room's hostel
        if not (request.user.is_superuser or selectors.list_assigned_hostels(request.user).filter(hall_id=room.hostel.hall_id).exists()):
             return Response({"detail": "Not authorized for this hostel."}, status=403)
             
        try:
            gr = services.register_guest_room_service(room.hostel, room, request.user)
            return Response(self.get_serializer(gr).data, status=201)
        except Exception as e:
            return Response({"detail": str(e)}, status=400)

    @action(detail=False, methods=['get'], url_path='available-rooms')
    def available_rooms(self, request):
        hall_id = request.query_params.get('hall_id')
        if not hall_id:
            return Response({"detail": "hall_id is required."}, status=400)
        rooms = selectors.list_available_rooms_for_guest_designation(hall_id)
        return Response(serializers.RoomSerializer(rooms, many=True).data)


class GuestBookingListCreateView(generics.ListCreateAPIView):
    """Student requests or standard listing of bookings."""
    permission_classes = [IsAuthenticated, HasActiveHostelAllotment]

    def get_serializer_class(self):
        if self.request.method == 'POST':
            return serializers.GuestRoomBookingCreateSerializer
        return serializers.GuestRoomBookingSerializer

    def get_queryset(self):
        filters = {}
        if 'status' in self.request.query_params:
            filters['status'] = self.request.query_params.get('status')
        if 'hostel' in self.request.query_params:
            filters['hostel'] = self.request.query_params.get('hostel')
            
        return selectors.list_guest_bookings_scoped(self.request.user, filters)

    def create(self, request, *args, **kwargs):
        print("INCOMING GUEST BOOKING DATA:", request.data)
        serializer = self.get_serializer(data=request.data)
        if not serializer.is_valid():
            print("GUEST BOOKING VALIDATION ERRORS:", serializer.errors)
        return super().create(request, *args, **kwargs)

    def perform_create(self, serializer):
        from rest_framework.exceptions import ValidationError
        try:
            student = selectors.get_student(self.request.user)
            if not student:
                raise ValidationError("Only students can request guest rooms.")
                
            allotment = selectors.get_active_allotment_by_student(student)
            if not allotment:
                raise ValidationError("You must be residing in a hostel to book a guest room.")
                
            hostel = allotment.hostel
            
            services.create_guest_booking_service(
                student=student,
                hostel=hostel,
                guest_data=serializer.validated_data,
                check_in_date=serializer.validated_data['check_in_date'],
                check_out_date=serializer.validated_data['check_out_date']
            )
        except Exception as e:
            raise ValidationError({"detail": str(e)})


class GuestBookingRetrieveUpdateView(generics.RetrieveAPIView):
    """Retrieve details of a specific guest booking."""
    permission_classes = [IsAuthenticated]
    serializer_class = serializers.GuestRoomBookingSerializer
    queryset = GuestRoomBooking.objects.all()


class GuestBookingApproveView(generics.GenericAPIView):
    """Approve or Reject a booking."""
    permission_classes = [IsWardenOrCaretaker | IsHostelSuperAdmin]
    serializer_class = serializers.GuestRoomBookingApprovalSerializer

    def post(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            booking = services.process_booking_decision_service(
                booking_id=pk,
                caretaker_user=request.user,
                decision=serializer.validated_data['decision'],
                remarks=serializer.validated_data.get('remarks', ''),
                room_id=serializer.validated_data.get('room_id')
            )
            return Response(serializers.GuestRoomBookingSerializer(booking).data)
        except Exception as e:
            return Response({"detail": str(e)}, status=400)


class GuestBookingCheckInView(generics.GenericAPIView):
    """Caretaker records guest arrival."""
    permission_classes = [IsWardenOrCaretaker | IsHostelSuperAdmin]
    serializer_class = serializers.GuestRoomCheckInSerializer

    def post(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            booking = services.process_checkin_service(
                booking_id=pk,
                caretaker_user=request.user,
                id_proof_type=serializer.validated_data['id_proof_type'],
                id_proof_number=serializer.validated_data['id_proof_number']
            )
            return Response(serializers.GuestRoomBookingSerializer(booking).data)
        except Exception as e:
            return Response({"detail": str(e)}, status=400)


class GuestBookingCheckOutView(generics.GenericAPIView):
    """Caretaker records guest departure and inspection."""
    permission_classes = [IsWardenOrCaretaker | IsHostelSuperAdmin]
    serializer_class = serializers.GuestRoomCheckOutSerializer

    def post(self, request, pk):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        try:
            booking, inspection = services.process_checkout_service(
                booking_id=pk,
                caretaker_user=request.user,
                condition_remarks=serializer.validated_data['condition_remarks'],
                damage_severity=serializer.validated_data['damage_severity'],
                damage_charge=serializer.validated_data['damage_charge']
            )
            return Response({
                "booking": serializers.GuestRoomBookingSerializer(booking).data,
                "inspection": serializers.GuestRoomInspectionSerializer(inspection).data
            })
        except Exception as e:
            return Response({"detail": str(e)}, status=400)


# ══════════════════════════════════════════════════════════════
# ══════════════════════════════════════════════════════════════
# NOTICE BOARD VIEWS (HM-WF-110)
# ══════════════════════════════════════════════════════════════

class NoticeListCreateView(generics.ListCreateAPIView):
    """
    List active notices or create a new notice (HM-WF-110).
    - Students: See scoped active notices.
    - Staff: See all notices for their assigned hostels.
    """
    permission_classes = [IsAuthenticated, HasActiveHostelAllotment]
    serializer_class = NoticeSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        from ..selectors import list_active_notices_for_student, list_notices_for_staff, is_user_warden_or_caretaker
        user = self.request.user
        if user.is_superuser or user.is_staff or is_user_warden_or_caretaker(user):
            return list_notices_for_staff(user)
        return list_active_notices_for_student(user)

    def create(self, request, *args, **kwargs):
        from ..services import create_notice
        from rest_framework import status
        from rest_framework.response import Response

        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        
        # Pre-process data for the service
        # Service expects 'hostel_id'
        data = serializer.validated_data.copy()
        hostel_obj = data.pop('hostel', None)
        data['hostel_id'] = hostel_obj.pk if hostel_obj else None
        
        attachment = request.FILES.get('attachment')
        
        # Call the service with validated and mapped data
        notice = create_notice(request.user, data, attachment=attachment)
        
        # Return serialized data of the created object
        serializer = self.get_serializer(notice)
        return Response(serializer.data, status=status.HTTP_201_CREATED)


class NoticeDetailView(generics.RetrieveUpdateDestroyAPIView):
    """
    Retrieve, update or delete a notice.
    Students: Mark as read on retrieval.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = NoticeSerializer

    def get_object(self):
        from ..selectors import get_notice
        notice = get_notice(self.kwargs['pk'])
        if not notice:
             from django.http import Http404
             raise Http404("Notice not found")
             
        # Mark as read for students on GET
        if self.request.method == 'GET' and not (self.request.user.is_staff or self.request.user.is_superuser):
            from ..services import mark_notice_as_read
            mark_notice_as_read(notice.id, self.request.user)
            
        return notice

    def perform_update(self, serializer):
        from ..services import update_notice
        attachment = self.request.FILES.get('attachment')
        update_notice(self.kwargs['pk'], self.request.data, self.request.user, attachment=attachment)

    def perform_destroy(self, instance):
        from ..services import delete_notice
        delete_notice(instance.id, self.request.user)


class NoticeHistoryView(generics.ListAPIView):
    """
    View archived or expired notices history.
    """
    permission_classes = [IsAuthenticated]
    serializer_class = NoticeSerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        from ..selectors import list_notice_history
        return list_notice_history(self.request.user)


# ══════════════════════════════════════════════════════════════
# NEW FEATURE VIEWS (Room Vacation & Extended Stay)
# ══════════════════════════════════════════════════════════════

from .serializers import RoomVacationRequestSerializer, ExtendedStayApplicationSerializer
from ..selectors import list_room_vacations, get_room_vacation, list_extended_stays, get_extended_stay

class RoomVacationListCreateView(generics.ListCreateAPIView):
    serializer_class = RoomVacationRequestSerializer
    permission_classes = [IsAuthenticated, HasActiveHostelAllotment]

    def get_queryset(self):
        filters = {}
        if not self.request.user.is_staff and not self.request.user.is_superuser:
            filters['student'] = getattr(self.request.user, 'student', None)
        return list_room_vacations(filters)

    def perform_create(self, serializer):
        serializer.save(student=self.request.user.student)

class RoomVacationDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = RoomVacationRequestSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        filters = {}
        if not self.request.user.is_staff and not self.request.user.is_superuser:
            filters['student'] = getattr(self.request.user, 'student', None)
        return list_room_vacations(filters)

class RoomVacationVerifyView(generics.UpdateAPIView):
    serializer_class = RoomVacationRequestSerializer
    permission_classes = [IsAdminUser]

    def update(self, request, *args, **kwargs):
        from ..services import process_room_vacation
        try:
            remarks = request.data.get('remarks', '')
            obj = process_room_vacation(kwargs['pk'], 'verify', remarks)
            return Response({'status': obj.status})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

class RoomVacationApproveView(generics.UpdateAPIView):
    serializer_class = RoomVacationRequestSerializer
    permission_classes = [IsAdminUser]

    def update(self, request, *args, **kwargs):
        from ..services import process_room_vacation
        try:
            remarks = request.data.get('remarks', '')
            obj = process_room_vacation(kwargs['pk'], 'approve', remarks)
            return Response({'status': obj.status})
        except Exception as e:
            return Response({'error': str(e)}, status=400)


class ExtendedStayListCreateView(generics.ListCreateAPIView):
    serializer_class = ExtendedStayApplicationSerializer
    permission_classes = [IsAuthenticated, HasActiveHostelAllotment]

    def get_queryset(self):
        filters = {}
        if not self.request.user.is_staff and not self.request.user.is_superuser:
            filters['student'] = getattr(self.request.user, 'student', None)
        return list_extended_stays(filters)

    def create(self, request, *args, **kwargs):
        from ..services import create_extended_stay
        try:
            serializer = self.get_serializer(data=request.data)
            serializer.is_valid(raise_exception=True)
            
            student = getattr(self.request.user, 'student', None)
            if not student:
                return Response({"error": "User is not a student."}, status=400)
                
            stay = create_extended_stay(
                student=student,
                start_date=serializer.validated_data['start_date'],
                end_date=serializer.validated_data['end_date'],
                reason=serializer.validated_data['reason']
            )
            return Response(ExtendedStayApplicationSerializer(stay).data, status=201)
        except Exception as e:
            return Response({'error': str(e)}, status=400)

class ExtendedStayDetailView(generics.RetrieveUpdateAPIView):
    serializer_class = ExtendedStayApplicationSerializer
    permission_classes = [IsAuthenticated]

    def get_queryset(self):
        filters = {}
        if not self.request.user.is_staff and not self.request.user.is_superuser:
            filters['student'] = getattr(self.request.user, 'student', None)
        return list_extended_stays(filters)

class ExtendedStayApproveView(generics.UpdateAPIView):
    serializer_class = ExtendedStayApplicationSerializer
    permission_classes = [IsAdminUser]
    
    def update(self, request, *args, **kwargs):
        try:
            obj = get_extended_stay(kwargs['pk'])
            obj.status = 'approved'
            obj.remarks = request.data.get('remarks', obj.remarks)
            obj.save()
            return Response({'status': 'approved'})
        except Exception as e:
            return Response({'error': str(e)}, status=400)

class ExtendedStayRejectView(generics.UpdateAPIView):
    serializer_class = ExtendedStayApplicationSerializer
    permission_classes = [IsAdminUser]
    
    def update(self, request, *args, **kwargs):
        try:
            obj = get_extended_stay(kwargs['pk'])
            obj.status = 'rejected'
            obj.remarks = request.data.get('remarks', obj.remarks)
            obj.save()
            return Response({'status': 'rejected'})
        except Exception as e:
            return Response({'error': str(e)}, status=400)


# ══════════════════════════════════════════════════════════════
# ATTENDANCE MANAGEMENT VIEWS
# ══════════════════════════════════════════════════════════════

class AttendanceByHostelView(generics.ListAPIView):
    """List attendance for a hostel on a specific date."""
    permission_classes = [IsWardenOrCaretaker]
    serializer_class = StudentAttendanceRecordSerializer

    def get_queryset(self):
        hall_id = self.request.query_params.get('hall_id')
        date_str = self.request.query_params.get('date')
        if not hall_id:
             return StudentAttendanceRecord.objects.none()
        
        if date_str:
            try:
                date = datetime.strptime(date_str, '%Y-%m-%d').date()
            except ValueError:
                date = timezone.now().date()
        else:
            date = timezone.now().date()
        
        return selectors.list_attendance_by_date(hall_id, date)


class AttendanceMarkView(generics.CreateAPIView):
    """Bulk mark attendance for a hall."""
    permission_classes = [IsWardenOrCaretaker]
    serializer_class = StudentAttendanceRecordSerializer

    def post(self, request, *args, **kwargs):
        date_str = request.data.get('date')
        attendance_data = request.data.get('attendance', [])
        
        if not date_str:
            return Response({'error': 'date is required'}, status=status.HTTP_400_BAD_REQUEST)
            
        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
            records = services.mark_attendance_bulk(date, attendance_data)
            serializer = self.get_serializer(records, many=True)
            return Response(serializer.data, status=status.HTTP_201_CREATED)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AttendanceBulkUploadView(generics.GenericAPIView):
    """Bulk mark attendance via Excel upload."""
    permission_classes = [IsWardenOrCaretaker]
    parser_classes = [parsers.MultiPartParser]

    def post(self, request, *args, **kwargs):
        hall_id = request.data.get('hall_id')
        date_str = request.data.get('date')
        excel_file = request.FILES.get('file')

        if not all([hall_id, date_str, excel_file]):
            return Response({'error': 'hall_id, date, and file are required.'}, status=status.HTTP_400_BAD_REQUEST)

        try:
            date = datetime.strptime(date_str, '%Y-%m-%d').date()
            result = services.process_attendance_excel(hall_id, date, excel_file)
            return Response(result, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({'error': str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AttendanceSummaryView(generics.ListAPIView):
    """Get attendance statistics for all students in a hostel."""
    permission_classes = [IsWardenOrCaretaker]
    serializer_class = serializers.AttendanceSummarySerializer
    pagination_class = StandardPagination

    def get_queryset(self):
        hall_id = self.request.query_params.get('hall_id')
        if not hall_id:
            from applications.academic_information.models import Student
            return Student.objects.none()
        return selectors.get_hostel_attendance_summary(hall_id)


class StudentAttendanceStatsView(generics.RetrieveAPIView):
    """Get personal attendance statistics and absence dates."""
    permission_classes = [IsStudent | IsWardenOrCaretaker]
    
    def get(self, request, *args, **kwargs):
        student_id = self.kwargs.get('pk')
        
        # If no PK provided, assume current student
        if not student_id:
            student = selectors.get_student(request.user)
            if not student:
                return Response({'error': 'Student profile not found.'}, status=status.HTTP_404_NOT_FOUND)
            student_id = student.pk
        
        # RBAC: Students only authorized for their own ID
        if not selectors.is_user_warden_or_caretaker(request.user):
            student = selectors.get_student(request.user)
            if str(student.pk) != str(student_id):
                 return Response({'error': 'Access denied.'}, status=status.HTTP_403_FORBIDDEN)

        stats = selectors.get_student_attendance_stats(student_id)
        absences = selectors.list_student_absences(student_id)
        absences_serializer = serializers.AbsenceDateSerializer(absences, many=True)
        
        return Response({
            'stats': stats,
            'absence_dates': [d['date'] for d in absences_serializer.data]
        })


# ══════════════════════════════════════════════════════════════
# HOSTEL SETUP FOUNDATION VIEWS
# ══════════════════════════════════════════════════════════════

from ..models import (
    HostelAuditLog, StaffRoleChoices, HostelStatusChoices as HostelOpStatusChoices
)
from ..permissions import IsHostelSuperAdmin, IsAssignedToHostel
from .serializers import (
    HostelSetupSerializer, HostelCreateSerializer, HostelStatusSerializer,
    StaffAssignmentSerializer, StaffAssignmentCreateSerializer,
    HostelAuditLogSerializer
)


class CreateHostelView(generics.CreateAPIView):
    """Create a new hostel (SuperAdmin only). Rooms auto-created via post_save signal."""
    permission_classes = [IsHostelSuperAdmin]
    serializer_class = HostelCreateSerializer

    def perform_create(self, serializer):
        hostel = serializer.save(created_by=self.request.user)
        # Write audit log
        HostelAuditLog.objects.create(
            hostel=hostel,
            action='HOSTEL_CREATED',
            performed_by=self.request.user,
            detail_json={
                'name': hostel.name,
                'type': hostel.type,
                'total_capacity': hostel.total_capacity,
                'floor_count': hostel.floor_count,
                'rooms_created': hostel.rooms_setup.count(),
            }
        )

    def create(self, request, *args, **kwargs):
        response = super().create(request, *args, **kwargs)
        # Return with full serializer
        hall_id = response.data.get('hall_id')
        hostel = Hostel.objects.get(hall_id=hall_id)
        return Response(
            HostelSetupSerializer(hostel).data,
            status=status.HTTP_201_CREATED
        )


class ListHostelsView(generics.ListAPIView):
    """
    List hostels with warden info.
    - SuperAdmins see all hostels.
    - Wardens and Caretakers see only their assigned hostels (modern or legacy).
    """
    permission_classes = [IsHostelSuperAdmin | IsWardenOrCaretaker]
    serializer_class = HostelSetupSerializer

    def get_queryset(self):
        user = self.request.user
        queryset = Hostel.objects.prefetch_related(
            'staff_assignments', 'staff_assignments__user', 'rooms_setup'
        )
        
        if user.is_superuser:
            return queryset.all()
        
        # Filter by assigned hostels (including legacy mapping)
        assigned_query = selectors.list_assigned_hostels(user)
        return queryset.filter(hall_id__in=assigned_query.values_list('hall_id', flat=True))


class RetrieveHostelView(generics.RetrieveAPIView):
    """Retrieve a single hostel's details."""
    permission_classes = [IsAssignedToHostel]
    serializer_class = HostelSetupSerializer

    def get_queryset(self):
        return Hostel.objects.prefetch_related(
            'staff_assignments', 'staff_assignments__user', 'rooms_setup'
        ).all()


class ManageHostelStatusView(generics.GenericAPIView):
    """
    Change hostel status (SuperAdmin only).

    Enforces:
    - BR-HM-008.a: Block deactivation if occupied rooms
    - BR-HM-008.b / BR-HM-019.a: Block activation without warden+caretaker
    - All changes written to HostelAuditLog
    """
    permission_classes = [IsHostelSuperAdmin]
    serializer_class = HostelStatusSerializer

    def patch(self, request, pk, *args, **kwargs):
        hostel = get_object_or_404(Hostel, pk=pk)
        serializer = self.get_serializer(
            data=request.data, context={'hostel': hostel}
        )
        serializer.is_valid(raise_exception=True)

        old_status = hostel.status
        new_status = serializer.validated_data['status']

        hostel.status = new_status
        hostel.save(update_fields=['status', 'updated_at'])

        # Write audit log
        HostelAuditLog.objects.create(
            hostel=hostel,
            action='STATUS_CHANGED',
            performed_by=request.user,
            detail_json={
                'from_status': old_status,
                'to_status': new_status,
            }
        )

        return Response(
            HostelSetupSerializer(hostel).data,
            status=status.HTTP_200_OK
        )


class AssignWardenView(generics.GenericAPIView):
    """
    Assign a warden to a hostel (SuperAdmin only).

    Deactivates any previous active warden for this hostel before creating
    the new assignment. Writes to HostelAuditLog.
    """
    permission_classes = [IsHostelSuperAdmin]
    serializer_class = StaffAssignmentCreateSerializer

    def post(self, request, pk, *args, **kwargs):
        hostel = get_object_or_404(Hostel, pk=pk)
        data = request.data.copy()
        data['role'] = StaffRoleChoices.WARDEN
        serializer = self.get_serializer(data=data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.get(id=serializer.validated_data['user_id'])

        try:
            assignment = services.assign_staff_to_hostel(
                hostel=hostel,
                staff_user=user,
                role=StaffRoleChoices.WARDEN,
                start_date=serializer.validated_data['start_date'],
                end_date=serializer.validated_data.get('end_date'),
                assigned_by=request.user
            )
            return Response(StaffAssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)
        except HostelManagementException as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class AssignCaretakerView(generics.GenericAPIView):
    """
    Assign a caretaker to a hostel (SuperAdmin only).

    Deactivates any previous active caretaker for this hostel before creating
    the new assignment. Writes to HostelAuditLog.
    """
    permission_classes = [IsHostelSuperAdmin]
    serializer_class = StaffAssignmentCreateSerializer

    def post(self, request, pk, *args, **kwargs):
        hostel = get_object_or_404(Hostel, pk=pk)
        data = request.data.copy()
        data['role'] = StaffRoleChoices.CARETAKER
        serializer = self.get_serializer(data=data)
        
        if not serializer.is_valid():
            return Response(serializer.errors, status=status.HTTP_400_BAD_REQUEST)

        user = User.objects.get(id=serializer.validated_data['user_id'])

        try:
            assignment = services.assign_staff_to_hostel(
                hostel=hostel,
                staff_user=user,
                role=StaffRoleChoices.CARETAKER,
                start_date=serializer.validated_data['start_date'],
                end_date=serializer.validated_data.get('end_date'),
                assigned_by=request.user
            )
            return Response(StaffAssignmentSerializer(assignment).data, status=status.HTTP_201_CREATED)
        except HostelManagementException as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)


class ReassignStaffView(generics.GenericAPIView):
    """
    Reassign staff on a hostel (SuperAdmin only).

    If removing the only Warden or Caretaker, a replacement must be provided
    in the same request. Both old_assignment_id and new user data required.
    """
    permission_classes = [IsHostelSuperAdmin]

    def post(self, request, pk, *args, **kwargs):
        hostel = get_object_or_404(Hostel, pk=pk)

        old_assignment_id = request.data.get('old_assignment_id')
        new_user_id = request.data.get('new_user_id')
        start_date = request.data.get('start_date')

        if not old_assignment_id or not new_user_id or not start_date:
            return Response(
                {'error': 'old_assignment_id, new_user_id, and start_date are required.'},
                status=status.HTTP_400_BAD_REQUEST
            )

        old_assignment = get_object_or_404(
            HostelStaffAssignment, pk=old_assignment_id, hostel=hostel
        )
        new_user = get_object_or_404(User, pk=new_user_id)

        role = old_assignment.role

        # Check: if removing the only active assignment of this role, block
        active_same_role = HostelStaffAssignment.objects.filter(
            hostel=hostel, role=role, is_active=True
        ).exclude(pk=old_assignment.pk).count()

        if active_same_role == 0 and hostel.status == HostelOpStatusChoices.ACTIVE:
            # Must be a replacement — which is what this endpoint does
            pass

        # Deactivate old
        old_assignment.is_active = False
        old_assignment.end_date = timezone.now().date()
        old_assignment.save()

        # Create new
        new_assignment = HostelStaffAssignment.objects.create(
            hostel=hostel,
            user=new_user,
            role=role,
            start_date=start_date,
            is_active=True,
            assigned_by=request.user
        )

        HostelAuditLog.objects.create(
            hostel=hostel,
            action='STAFF_REASSIGNED',
            performed_by=request.user,
            detail_json={
                'role': role,
                'old_user_id': old_assignment.user.id,
                'old_user_name': old_assignment.user.get_full_name() or old_assignment.user.username,
                'new_user_id': new_user.id,
                'new_user_name': new_user.get_full_name() or new_user.username,
            }
        )

        return Response(
            StaffAssignmentSerializer(new_assignment).data,
            status=status.HTTP_200_OK
        )


class ListStaffAssignmentsView(generics.ListAPIView):
    """
    List staff assignments for a hostel.
    - Accessible only by SuperAdmins or assigned Wardens/Caretakers.
    """
    permission_classes = [IsHostelSuperAdmin | IsAssignedToHostel]
    serializer_class = serializers.StaffAssignmentSerializer

    def get_queryset(self):
        hostel_id = self.kwargs.get('pk')
        return HostelStaffAssignment.objects.filter(
            hostel_id=hostel_id
        ).select_related('user', 'hostel', 'assigned_by')


class RemoveStaffAssignmentView(generics.GenericAPIView):
    """
    Remove (deactivate) an active staff assignment (SuperAdmin only).
    """
    permission_classes = [IsHostelSuperAdmin]

    def post(self, request, pk, *args, **kwargs):
        assignment = get_object_or_404(HostelStaffAssignment, pk=pk, is_active=True)
        hostel = assignment.hostel
        
        assignment.is_active = False
        assignment.end_date = timezone.now().date()
        assignment.save()

        # Write audit log
        HostelAuditLog.objects.create(
            hostel=hostel,
            action=f'{assignment.role.upper()}_REMOVED',
            performed_by=request.user,
            detail_json={
                'user_id': assignment.user.id,
                'username': assignment.user.username,
                'assignment_id': assignment.id
            }
        )

        return Response(
            serializers.HostelSetupSerializer(hostel).data,
            status=status.HTTP_200_OK
        )


class DeleteHostelView(generics.DestroyAPIView):
    """
    Permanently delete a hostel (SuperAdmin only).
    CASCADE deletes rooms, assignments, etc.
    """
    permission_classes = [IsHostelSuperAdmin]
    queryset = Hostel.objects.all()

    def perform_destroy(self, instance):
        # We can't write an audit log for an object we just deleted if it references it by FK
        # So we log it first without the FK if necessary, or just rely on global logs
        # Actually, since our AuditLog is CASCADE, if we delete the hostel, 
        # the audit log entries for that hostel will ALSO be deleted if they have a FK to it.
        # This is a drawback of CASCADE audit logs.
        super().perform_destroy(instance)

# ══════════════════════════════════════════════════════════════
# SEMESTER END VACATION VIEWS
# ══════════════════════════════════════════════════════════════

class BulkHostelVacationView(generics.GenericAPIView):
    """
    Process bulk vacation for multiple hostels (SuperAdmin only).
    Permanently unallocates students and resets rooms.
    """
    permission_classes = [IsHostelSuperAdmin]
    serializer_class = BulkHostelVacationSerializer

    def post(self, request, *args, **kwargs):
        serializer = self.get_serializer(data=request.data)
        serializer.is_valid(raise_exception=True)

        try:
            count = services.process_bulk_hostel_vacation(
                hostel_ids=serializer.validated_data['hostel_ids'],
                performed_by=request.user
            )
            return Response({
                "message": f"Successfully vacated {count} hostels.",
                "hostels_affected": count
            }, status=status.HTTP_200_OK)
        except Exception as e:
            return Response({"error": str(e)}, status=status.HTTP_400_BAD_REQUEST)

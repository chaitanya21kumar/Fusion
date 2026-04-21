"""
API URL Configuration for Hostel Management Module

CRITICAL RULES:
- Only router definitions and URL patterns here
- No views, no logic
- Use viewsets with DefaultRouter for RESTful consistency
"""

from django.urls import path, include
from . import views

app_name = 'hostel_management_api'

from rest_framework.routers import DefaultRouter

# ══════════════════════════════════════════════════════════════
# ROUTER CONFIGURATION
# ══════════════════════════════════════════════════════════════
inventory_router = DefaultRouter()
inventory_router.register('items', views.InventoryItemViewSet, basename='inventory-item')
inventory_router.register('discrepancies', views.InventoryDiscrepancyViewSet, basename='inventory-discrepancy')
inventory_router.register('audit-trail', views.InventoryAuditTrailViewSet, basename='inventory-audit-trail')
inventory_router.register('resource-requests', views.ResourceRequestViewSet, basename='resource-request')

guest_registry_router = DefaultRouter()
guest_registry_router.register('registry', views.GuestRoomRegistryViewSet, basename='guest-room-registry')

# ══════════════════════════════════════════════════════════════
# HOSTEL SETUP FOUNDATION ROUTES (Modernized)
# ══════════════════════════════════════════════════════════════
hostel_setup_patterns = [
    path('', views.ListHostelsView.as_view(), name='hostel-list'),
    path('create/', views.CreateHostelView.as_view(), name='hostel-create'),
    path('bulk-vacate/', views.BulkHostelVacationView.as_view(), name='hostel-bulk-vacate'),
    path('<str:pk>/', views.RetrieveHostelView.as_view(), name='hostel-detail'),
    path('<str:pk>/rooms/', views.ListRoomsByHostelView.as_view(), name='hostel-rooms'),
    path('<str:pk>/status/', views.ManageHostelStatusView.as_view(), name='hostel-status'),
    path('<str:pk>/assign-warden/', views.AssignWardenView.as_view(), name='hostel-assign-warden'),
    path('<str:pk>/assign-caretaker/', views.AssignCaretakerView.as_view(), name='hostel-assign-caretaker'),
    path('<str:pk>/reassign-staff/', views.ReassignStaffView.as_view(), name='hostel-reassign-staff'),
    path('<str:pk>/staff/', views.ListStaffAssignmentsView.as_view(), name='hostel-staff-list'),
    path('staff-assignments/<int:pk>/remove/', views.RemoveStaffAssignmentView.as_view(), name='hostel-staff-remove'),
    path('<str:pk>/delete/', views.DeleteHostelView.as_view(), name='hostel-delete'),
    path('<str:pk>/bulk-batch-allot/', views.BulkBatchAllocationView.as_view(), name='hostel-bulk-batch-allot'),
]

admin_patterns = [
    path('faculty/', views.FacultyListView.as_view(), name='faculty-list'),
    path('staff/', views.StaffListView.as_view(), name='staff-list'),
]

# ══════════════════════════════════════════════════════════════
# ACCOMMODATION REQUEST & ALLOTMENT ROUTES (HM-WF-103)
# ══════════════════════════════════════════════════════════════
accommodation_patterns = [
    path('windows/', views.ListWindowsView.as_view(), name='windows-list'),
    path('request/', views.SubmitAccommodationRequestView.as_view(), name='request-submit'),
    path('requests/', views.ListRequestsView.as_view(), name='requests-list'),
    path('capacity/', views.RoomCapacityDashboardView.as_view(), name='capacity-dashboard'),
    path('bulk-allot/', views.BulkAllotmentView.as_view(), name='bulk-allot'),
    path('my-allotment/', views.MyAllotmentView.as_view(), name='my-allotment'),
    path('allotments/', views.RoomAllotmentListView.as_view(), name='allotment-list'),
    path('allotments/<int:pk>/delete/', views.RoomAllotmentDestroyView.as_view(), name='allotment-delete'),
]

# ══════════════════════════════════════════════════════════════
# LEAVE MANAGEMENT ROUTES (HM-WF-101)
# ══════════════════════════════════════════════════════════════
leave_patterns = [
    path('', views.LeaveListCreateView.as_view(), name='leave-list-create'),
    path('my/', views.LeaveMyListView.as_view(), name='leave-my-list'),
    path('<int:pk>/', views.LeaveRetrieveUpdateView.as_view(), name='leave-detail'),
    path('<int:pk>/approve/', views.LeaveApproveView.as_view(), name='leave-approve'),
    path('<int:pk>/reject/', views.LeaveRejectView.as_view(), name='leave-reject'),
]

# ══════════════════════════════════════════════════════════════
# COMPLAINT MANAGEMENT ROUTES (HM-WF-102)
# ══════════════════════════════════════════════════════════════
complaint_patterns = [
    path('', views.ComplaintListCreateView.as_view(), name='complaint-list-create'),
    path('<int:pk>/', views.ComplaintDetailView.as_view(), name='complaint-detail'),
    path('<int:pk>/start/', views.StartComplaintView.as_view(), name='complaint-start'),
    path('<int:pk>/escalate/', views.EscalateComplaintView.as_view(), name='complaint-escalate'),
    path('<int:pk>/resolve/', views.ResolveComplaintView.as_view(), name='complaint-resolve'),
    path('report/', views.ComplaintReportView.as_view(), name='complaint-report'),
]

# ══════════════════════════════════════════════════════════════
# ROOM CHANGE ROUTES (HM-WF-104)
# ══════════════════════════════════════════════════════════════
room_change_patterns = [
    path('', views.RoomChangeListCreateView.as_view(), name='room-change-list-create'),
    path('<int:pk>/', views.RoomChangeRetrieveView.as_view(), name='room-change-detail'),
    path('<int:pk>/approve/', views.RoomChangeApproveView.as_view(), name='room-change-approve'),
    path('<int:pk>/reject/', views.RoomChangeRejectView.as_view(), name='room-change-reject'),
]

# ══════════════════════════════════════════════════════════════
# FINE MANAGEMENT ROUTES (HM-WF-105)
# ══════════════════════════════════════════════════════════════
fine_patterns = [
    path('', views.FineListCreateView.as_view(), name='fine-list-create'),
    path('repeat-offenders/', views.RepeatOffendersView.as_view(), name='fine-repeat-offenders'),
    path('report/', views.FineReportView.as_view(), name='fine-report'),
    path('student/<str:roll_number>/', views.StudentDetailByRollView.as_view(), name='student-detail-by-roll'),
    path('<int:pk>/', views.FineRetrieveView.as_view(), name='fine-detail'),
    path('<int:pk>/mark-paid/', views.FineMarkPaidView.as_view(), name='fine-mark-paid'),
    path('<int:pk>/waive/', views.FineWaiveView.as_view(), name='fine-waive'),
]

# ══════════════════════════════════════════════════════════════
# STAFF SCHEDULE ROUTES (HM-WF-107)
# ══════════════════════════════════════════════════════════════
schedule_patterns = [
    path('', views.StaffScheduleListCreateView.as_view(), name='schedule-list-create'),
    path('<int:pk>/', views.StaffScheduleRetrieveUpdateDestroyView.as_view(), name='schedule-detail'),
]

# ══════════════════════════════════════════════════════════════
# INVENTORY MANAGEMENT ROUTES (HM-WF-108)
# ══════════════════════════════════════════════════════════════
inventory_patterns = [
    path('', include(inventory_router.urls)),
]

# ══════════════════════════════════════════════════════════════
# NOTICE BOARD ROUTES (HM-WF-110)
# ══════════════════════════════════════════════════════════════
notice_patterns = [
    path('', views.NoticeListCreateView.as_view(), name='notice-list'),
    path('<int:pk>/', views.NoticeDetailView.as_view(), name='notice-detail'),
    path('history/', views.NoticeHistoryView.as_view(), name='notice-history'),
]

guest_booking_patterns = [
    path('', include(guest_registry_router.urls)),
    path('policy/<str:hall_id>/', views.GuestRoomPolicyView.as_view(), name='guest-room-policy'),
    path('bookings/', views.GuestBookingListCreateView.as_view(), name='guest-booking-list-create'),
    path('bookings/<int:pk>/', views.GuestBookingRetrieveUpdateView.as_view(), name='guest-booking-detail'),
    path('bookings/<int:pk>/approve/', views.GuestBookingApproveView.as_view(), name='guest-booking-approve'),
    path('bookings/<int:pk>/check-in/', views.GuestBookingCheckInView.as_view(), name='guest-booking-check-in'),
    path('bookings/<int:pk>/check-out/', views.GuestBookingCheckOutView.as_view(), name='guest-booking-check-out'),
]

# ══════════════════════════════════════════════════════════════
# ATTENDANCE MANAGEMENT ROUTES
# ══════════════════════════════════════════════════════════════
attendance_patterns = [
    path('hostel/<str:hall_id>/', views.AttendanceByHostelView.as_view(), name='attendance-list'),
    path('mark/', views.AttendanceMarkView.as_view(), name='attendance-mark'),
    path('upload/', views.AttendanceBulkUploadView.as_view(), name='attendance-upload'),
    path('summary/', views.AttendanceSummaryView.as_view(), name='attendance-summary'),
    path('student/', views.StudentAttendanceStatsView.as_view(), name='attendance-student-stats'),
    path('student/<str:pk>/', views.StudentAttendanceStatsView.as_view(), name='attendance-student-stats-pk'),
]

# ══════════════════════════════════════════════════════════════
# NEW FEATURE ROUTES (Room Vacation & Extended Stay)
# ══════════════════════════════════════════════════════════════
vacation_patterns = [
    path('', views.RoomVacationListCreateView.as_view(), name='vacation-list-create'),
    path('<int:pk>/', views.RoomVacationDetailView.as_view(), name='vacation-detail'),
    path('<int:pk>/verify/', views.RoomVacationVerifyView.as_view(), name='vacation-verify'),
    path('<int:pk>/approve/', views.RoomVacationApproveView.as_view(), name='vacation-approve'),
]

extended_stay_patterns = [
    path('', views.ExtendedStayListCreateView.as_view(), name='extendedstay-list-create'),
    path('<int:pk>/', views.ExtendedStayDetailView.as_view(), name='extendedstay-detail'),
    path('<int:pk>/approve/', views.ExtendedStayApproveView.as_view(), name='extendedstay-approve'),
    path('<int:pk>/reject/', views.ExtendedStayRejectView.as_view(), name='extendedstay-reject'),
]

# ══════════════════════════════════════════════════════════════
# MAIN URL PATTERNS - Namespace organization
# ══════════════════════════════════════════════════════════════
urlpatterns = [
    path('hostels/', include((hostel_setup_patterns, 'hostels-setup'))),
    path('admin/', include((admin_patterns, 'admin'))),
    path('leaves/', include((leave_patterns, 'leaves'))),
    path('complaints/', include((complaint_patterns, 'complaints'))),
    path('accommodation/', include((accommodation_patterns, 'accommodation'))),
    path('room-changes/', include((room_change_patterns, 'room-changes'))),
    path('fines/', include((fine_patterns, 'fines'))),
    path('schedules/', include((schedule_patterns, 'schedules'))),
    path('inventory/', include((inventory_patterns, 'inventory'))),
    path('notices/', include((notice_patterns, 'notices'))),
    path('guest-bookings/', include((guest_booking_patterns, 'guest-bookings'))),
    path('attendance/', include((attendance_patterns, 'attendance'))),
    path('vacations/', include((vacation_patterns, 'vacations'))),
    path('extended-stays/', include((extended_stay_patterns, 'extended-stays'))),
]

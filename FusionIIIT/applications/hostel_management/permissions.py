"""
Hostel Management Permissions

Hostel-scoped permission classes for the setup foundation chunk.
These enforce role-based access control across all hostel setup endpoints.
"""

from rest_framework.permissions import BasePermission
from .models import HostelStaffAssignment
from . import selectors


class IsHostelSuperAdmin(BasePermission):
    """
    Permission for Super Admin role.

    Grants full CRUD on hostels, staff assignment, and status changes.
    Checks request.user.is_superuser (consistent with existing IsSuperAdmin pattern).
    """
    message = "Only Super Admins can perform this action."

    def has_permission(self, request, view):
        return bool(    
            request.user and 
            request.user.is_authenticated and 
            request.user.is_superuser
        )


class IsAssignedToHostel(BasePermission):
    """
    Permission for Warden/Caretaker scoped to a specific hostel.

    Checks HostelStaffAssignment for the requesting user with is_active=True
    on the hostel identified by the `pk` URL kwarg.

    Wardens and Caretakers get read-only access to hostel config
    within their assigned hostel.
    """
    message = "You are not assigned to this hostel."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False

        # Super admins always pass
        if request.user.is_superuser:
            return True

        hostel_id = view.kwargs.get('pk')
        if not hostel_id:
            return False

        # Check robust list of assigned hostels for the user
        assigned_hostels = selectors.list_assigned_hostels(request.user)
        return assigned_hostels.filter(hall_id=hostel_id).exists()


class IsWardenOrAdmin(BasePermission):
    """
    Permission for Super Admin OR assigned Warden of the request's hostel.
    Used for reviewing resource requests.
    """
    message = "You only have review authority over requests from your assigned hostels."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        if request.user.is_superuser:
            return True
        # Wardens can view lists; object-level check handles approval
        return selectors.is_user_warden_or_caretaker(request.user)

    def has_object_permission(self, request, view, obj):
        if request.user.is_superuser:
            return True
        
        # Ensure user is a warden of the hostel the request belongs to
        if not selectors.is_user_warden(request.user):
            return False

        assigned_hostels = selectors.list_assigned_hostels(request.user)
        # Check if the request's hostel is in user's assigned list
        hostel_id = getattr(obj, 'hostel_id', None) or getattr(obj.hostel, 'hall_id', None)
        return assigned_hostels.filter(hall_id=hostel_id).exists()


class HasActiveHostelAllotment(BasePermission):
    """
    Permission for Students who have an active room allotment.
    Blocks unallotted students from accessing residency-only features.
    """
    message = "You must be allocated to a hostel to access this feature."

    def has_permission(self, request, view):
        if not (request.user and request.user.is_authenticated):
            return False
        
        # Staff, Super Admins, and Warden/Caretakers always pass
        if request.user.is_staff or request.user.is_superuser or selectors.is_user_warden_or_caretaker(request.user):
            return True

        # Check if student has active allotment
        from applications.academic_information.models import Student
        from .models import RoomAllotment
        
        student = Student.objects.filter(id__user=request.user).first()
        if not student:
             return False
             
        return RoomAllotment.objects.filter(student=student, is_active=True).exists()

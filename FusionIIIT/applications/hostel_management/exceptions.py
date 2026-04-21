"""
Hostel Management Custom Exceptions

Custom exception classes for the hostel_management app.
Used for business logic validation and error handling.
"""


class HostelManagementException(Exception):
    """Base exception for hostel management module."""


# ══════════════════════════════════════════════════════════════
# HM-WF-101: LEAVE MANAGEMENT EXCEPTIONS
# ══════════════════════════════════════════════════════════════

class LeaveEligibilityError(HostelManagementException):
    """Raised when student is not eligible to apply for leave."""


class LeaveDateValidationError(HostelManagementException):
    """Raised when leave dates are invalid."""


# ══════════════════════════════════════════════════════════════
# HM-WF-102: COMPLAINT MANAGEMENT EXCEPTIONS
# ══════════════════════════════════════════════════════════════

class ComplaintError(HostelManagementException):
    """Raised when there's an error in complaint management."""


# ══════════════════════════════════════════════════════════════
# HM-WF-103 & HM-WF-104: ROOM ALLOCATION & CHANGE EXCEPTIONS
# ══════════════════════════════════════════════════════════════

class RoomAllocationError(HostelManagementException):
    """Raised when there's an error in room allocation."""


class RoomChangeError(HostelManagementException):
    """Raised when there's an error in room change process."""


# ══════════════════════════════════════════════════════════════
# HM-WF-105: FINE MANAGEMENT EXCEPTIONS
# ══════════════════════════════════════════════════════════════

class FineError(HostelManagementException):
    """Raised when there's an error in fine management."""


# ══════════════════════════════════════════════════════════════
# HM-WF-108: INVENTORY MANAGEMENT EXCEPTIONS
# ══════════════════════════════════════════════════════════════

class InventoryError(HostelManagementException):
    """Raised when there's an error in inventory management."""


# ══════════════════════════════════════════════════════════════
# HM-WF-110: NOTICE BOARD EXCEPTIONS
# ══════════════════════════════════════════════════════════════

class NoticeBoardError(HostelManagementException):
    """Raised when there's an error in notice board management."""


# ══════════════════════════════════════════════════════════════
# HM-WF-112: GUEST ROOM BOOKING EXCEPTIONS
# ══════════════════════════════════════════════════════════════

class GuestRoomBookingError(HostelManagementException):
    """Raised when there's an error in guest room booking."""

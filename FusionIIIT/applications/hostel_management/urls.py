"""
URL Configuration for Hostel Management Module.

Routes all requests to the API module.
"""

from django.urls import path, include

app_name = 'hostel_management'

urlpatterns = [
    # Include all API routes
    path('api/', include('applications.hostel_management.api.urls')),
]

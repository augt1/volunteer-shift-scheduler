from django.urls import path
from . import views

urlpatterns = [
    path("", views.week_view, name="week_view"),
    path("day/<int:year>/<int:month>/<int:day>/", views.location_day_view, name="location_day_view"),
    path("add-shift/", views.add_shift_modal, name="add_shift_modal"),
    path("shifts/<int:shift_id>/edit", views.edit_shift_modal, name="edit_shift_modal"),
    path("shifts/<int:shift_id>/assign", views.assign_volunteers_modal, name="assign_volunteers_modal"),
    path("assign-volunteer/<int:shift_id>/", views.assign_volunteer_modal, name="assign_volunteer_modal"),
    path("assign-volunteer/<int:shift_id>/save/", views.assign_volunteer, name="assign_volunteer"),
    path("unassign-volunteer/<int:shift_id>/<int:volunteer_id>/", views.unassign_volunteer, name="unassign_volunteer"),
    path("close-modal/", views.close_modal, name="close_modal"),
    path("manage-volunteer-positions/<int:volunteer_id>/", views.manage_volunteer_positions, name="manage_volunteer_positions"),
]

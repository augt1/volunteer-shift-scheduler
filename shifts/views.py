from collections import defaultdict
from datetime import datetime, time, timedelta
from itertools import groupby
from operator import attrgetter

from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.template.loader import render_to_string
from django.utils.html import strip_tags
from django.conf import settings
from django.http import HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.urls import reverse
from django.http import HttpRequest

from events.models import Event
from volunteers.models import Volunteer

from .models import Location, Position, PositionVolunteer, Shift, ShiftVolunteer


@login_required
def week_view(request):
    # Get the current event
    current_event = Event.objects.latest("start_date")

    # Get the requested date or default to event start date
    date_str = request.GET.get("date")
    if date_str:
        current_date = datetime.strptime(date_str, "%Y-%m-%d").date()
    else:
        current_date = current_event.start_date

    # Get all dates for the event
    event_dates = []
    current = current_event.start_date
    while current <= current_event.end_date:
        event_dates.append(current)
        current += timedelta(days=1)

    # Get selected location from query params or default to first
    locations = Location.objects.filter(event=current_event)
    location_id = request.GET.get("location")
    if location_id:
        try:
            selected_location = locations.get(id=location_id)
        except Location.DoesNotExist:
            selected_location = locations.first()
    else:
        selected_location = locations.first()

    # Generate hour slots from 10am to 5am next day
    hour_slots = []
    for hour in range(6, 24):  # 10am to 11:59pm
        hour_slots.append(time(hour, 0))
    for hour in range(0, 6):  # 12am to 5am next day
        hour_slots.append(time(hour, 0))

    # Create a mapping of hours to their position in the grid
    hour_to_position = {slot: idx for idx, slot in enumerate(hour_slots)}

    # Get all shifts for the selected location
    shifts = (
        Shift.objects.filter(event=current_event, location=selected_location)
        .select_related("position")
        .prefetch_related("volunteers")
    )

    # Organize shifts by date and calculate their grid positions
    shifts_by_date = {}
    for date in event_dates:
        date_shifts = shifts.filter(date=date)
        shifts_by_hour = {slot: [] for slot in hour_slots}

        # Group shifts by their time ranges to handle overlaps
        shift_groups = []  # List of lists of overlapping shifts

        for shift in date_shifts:
            # Handle shifts that span to next day
            shift_start = shift.start_time
            if shift_start.hour < 5:  # If shift starts between 12am-5am
                # It belongs to previous day's schedule
                shift_date = date - timedelta(days=1)
            else:
                shift_date = date

            if shift_date == date:
                # Find the start position
                start_hour = time(shift_start.hour, 0)
                if start_hour in hour_to_position:
                    start_pos = hour_to_position[start_hour]

                    # Calculate end position and row span
                    end_hour = shift.end_time.hour
                    if end_hour < 5:  # If ends next day before 5am
                        end_hour += 24
                    elif end_hour < 10:  # If ends next day after 5am
                        end_hour = 29  # 5am position

                    # Calculate how many hour slots this shift spans
                    if shift_start.hour < 5:
                        start_hour_24 = shift_start.hour + 24
                    else:
                        start_hour_24 = shift_start.hour
                    row_span = end_hour - start_hour_24

                    # Add shift with its position info
                    shift.grid_row_start = start_pos + 1  # 1-based for CSS grid
                    shift.grid_row_span = max(1, row_span)  # Ensure at least 1

                    # Find overlapping group or create new one
                    added_to_group = False
                    for group in shift_groups:
                        # Check if this shift overlaps with any shift in the group
                        overlaps = False
                        for existing_shift in group:
                            if (
                                shift_start < existing_shift.end_time
                                and shift.end_time > existing_shift.start_time
                            ):
                                overlaps = True
                                break

                        if overlaps:
                            group.append(shift)
                            added_to_group = True
                            # Update all shifts in this group to have same total_columns
                            total_columns = len(group)
                            for idx, s in enumerate(group):
                                s.column = idx  # Distribute shifts across columns
                                s.total_columns = total_columns
                            break

                    if not added_to_group:
                        # Create new group for this shift
                        shift_groups.append([shift])
                        shift.column = 0
                        shift.total_columns = 1

                    shifts_by_hour[start_hour].append(shift)

        # No need for additional column calculation since we do it during group assignment
        shifts_by_date[date] = shifts_by_hour

    return render(
        request,
        "shifts/calendar_week_view.html",
        {
            "current_event": current_event,
            "event_dates": event_dates,
            "shifts_by_date": shifts_by_date,
            "hour_slots": hour_slots,
            "locations": locations,
            "selected_location": selected_location,
            "current_date": current_date,
        },
    )


@login_required
def location_day_view(request, year, month, day):
    # Get the current event
    current_event = Event.objects.latest("start_date")

    # Create the requested date
    current_date = datetime(year, month, day).date()

    # Calculate next and previous days
    next_day = current_date + timedelta(days=1)
    prev_day = current_date - timedelta(days=1)

    # Only show navigation if within event dates
    show_next = next_day <= current_event.end_date
    show_prev = prev_day >= current_event.start_date

    # Generate hour slots from 6am to 5am next day
    hour_slots = []
    for hour in range(6, 24):  # 6am to 11:59pm
        hour_slots.append(time(hour, 0))
    for hour in range(0, 6):  # 12am to 5am next day
        hour_slots.append(time(hour, 0))

    # Create a mapping of hours to their position in the grid
    hour_to_position = {slot: idx for idx, slot in enumerate(hour_slots)}

    # Get all locations for this event
    locations = Location.objects.filter(event=current_event)

    # Get all shifts for the current date
    shifts = (
        Shift.objects.filter(date=current_date, event=current_event)
        .select_related("position")
        .prefetch_related("volunteers")
    )

    # Organize shifts by location and calculate their grid positions
    shifts_by_location = {}
    for location in locations:
        location_shifts = shifts.filter(location=location)
        shifts_by_hour = {slot: [] for slot in hour_slots}

        # Group shifts by their time ranges to handle overlaps
        shift_groups = []  # List of lists of overlapping shifts

        for shift in location_shifts:
            # Handle shifts that span to next day
            shift_start = shift.start_time
            if shift_start.hour < 5:  # If shift starts between 12am-5am
                # It belongs to previous day's schedule
                shift_date = current_date - timedelta(days=1)
            else:
                shift_date = current_date

            if shift_date == current_date:
                # Find the start position
                start_hour = time(shift_start.hour, 0)
                if start_hour in hour_to_position:
                    start_pos = hour_to_position[start_hour]

                    # Calculate end position and row span
                    end_hour = shift.end_time.hour
                    if end_hour < 5:  # If ends next day before 5am
                        end_hour += 24
                    elif end_hour < 6:  # If ends next day after 5am
                        end_hour = 29  # 5am position

                    # Calculate how many hour slots this shift spans
                    if shift_start.hour < 5:
                        start_hour_24 = shift_start.hour + 24
                    else:
                        start_hour_24 = shift_start.hour
                    row_span = end_hour - start_hour_24

                    # Add shift with its position info
                    shift.grid_row_start = start_pos + 1  # 1-based for CSS grid
                    shift.grid_row_span = max(1, row_span)  # Ensure at least 1

                    # Find overlapping group or create new one
                    added_to_group = False
                    for group in shift_groups:
                        # Check if this shift overlaps with any shift in the group
                        overlaps = False
                        for existing_shift in group:
                            if (
                                shift_start < existing_shift.end_time
                                and shift.end_time > existing_shift.start_time
                            ):
                                overlaps = True
                                break

                        if overlaps:
                            group.append(shift)
                            added_to_group = True
                            # Update all shifts in this group to have same total_columns
                            total_columns = len(group)
                            for idx, s in enumerate(group):
                                s.column = idx  # Distribute shifts across columns
                                s.total_columns = total_columns
                            break

                    if not added_to_group:
                        # Create new group for this shift
                        shift_groups.append([shift])
                        shift.column = 0
                        shift.total_columns = 1

                    shifts_by_hour[start_hour].append(shift)

        shifts_by_location[location] = shifts_by_hour

    return render(
        request,
        "shifts/calendar_day_view.html",
        {
            "current_event": current_event,
            "current_date": current_date,
            "hour_slots": hour_slots,
            "locations": locations,
            "shifts_by_location": shifts_by_location,
            "show_next": show_next,
            "show_prev": show_prev,
            "next_day": next_day,
            "prev_day": prev_day,
        },
    )


@login_required
def assign_volunteer_modal(request, shift_id):
    shift = get_object_or_404(Shift, id=shift_id)
    # Only show volunteers that are assigned to this position
    available_volunteers = (
        Volunteer.objects.filter(available_positions=shift.position)
        .exclude(shifts=shift)
        .order_by("first_name", "last_name")
    )

    return render(
        request,
        "shifts/assign_volunteer_modal.html",
        {
            "shift": shift,
            "available_volunteers": available_volunteers,
        },
    )


@login_required
def assign_volunteer(request, shift_id):
    if request.method != "POST":
        return HttpResponseBadRequest()

    shift = get_object_or_404(Shift, id=shift_id)
    volunteer_id = request.POST.get("volunteer_id")

    if not volunteer_id:
        return HttpResponseBadRequest("No volunteer selected")

    volunteer = get_object_or_404(Volunteer, id=volunteer_id)

    # Check if shift is full
    if shift.volunteers.count() >= shift.max_volunteers:
        return HttpResponseBadRequest("Shift is full")

    # Check if volunteer is already assigned
    if shift.volunteers.filter(id=volunteer.id).exists():
        return HttpResponseBadRequest("Volunteer already assigned to this shift")

    # Assign the volunteer
    ShiftVolunteer.objects.create(
        shift=shift, volunteer=volunteer, assigned_by=request.user
    )

    # Return the updated shift card HTML and close the modal
    response = render(
        request,
        "shifts/shift_card.html",
        {
            "shift": shift,
        },
    )
    response["HX-Trigger"] = "closeModal"
    return response


@login_required
def unassign_volunteer(request, shift_id, volunteer_id):
    if request.method != "DELETE":
        return HttpResponseBadRequest()

    shift = get_object_or_404(Shift, id=shift_id)
    volunteer = get_object_or_404(Volunteer, id=volunteer_id)

    # Remove the volunteer
    ShiftVolunteer.objects.filter(shift=shift, volunteer=volunteer).delete()

    # Return the updated shift card HTML
    return render(
        request,
        "shifts/shift_card.html",
        {
            "shift": shift,
        },
    )


@login_required
def close_modal(request):
    return HttpResponse("")  # Return empty response to clear the modal


@login_required
def manage_volunteer_positions(request, volunteer_id):
    volunteer = get_object_or_404(Volunteer, id=volunteer_id)
    event = Event.objects.latest("start_date")  # Get the most recent event

    if request.method == "POST":
        position_ids = request.POST.getlist("positions")
        # Clear existing positions and add new ones
        PositionVolunteer.objects.filter(volunteer=volunteer).delete()
        for position_id in position_ids:
            position = Position.objects.get(id=position_id)
            PositionVolunteer.objects.create(
                volunteer=volunteer, position=position, assigned_by=request.user
            )
        return redirect("volunteer_list")

    positions = Position.objects.filter(event=event)
    assigned_positions = set(volunteer.available_positions.values_list("id", flat=True))

    return render(
        request,
        "shifts/manage_volunteer_positions.html",
        {
            "volunteer": volunteer,
            "positions": positions,
            "assigned_positions": assigned_positions,
        },
    )


@login_required
def add_shift_modal(request):
    if request.method == "POST":
        # Create the shift
        position = get_object_or_404(Position, id=request.POST.get("position"))
        date = datetime.strptime(request.POST.get("date"), "%Y-%m-%d").date()
        location = get_object_or_404(Location, id=request.POST.get("location"))
        start_time = datetime.strptime(request.POST.get("start_time"), "%H:%M").time()
        end_time = datetime.strptime(request.POST.get("end_time"), "%H:%M").time()
        max_volunteers = int(request.POST.get("max_volunteers", 1))
        event = get_object_or_404(Event, id=request.POST.get("event"))

        shift = Shift.objects.create(
            position=position,
            date=date,
            location=location,
            start_time=start_time,
            end_time=end_time,
            max_volunteers=max_volunteers,
            event=event,
        )

        # Check if we're in day view or week view based on the referer and current URL
        referer = request.META.get("HTTP_REFERER", "")
        current_path = request.path
        is_day_view = "day/" in referer or "day/" in current_path

        if is_day_view:
            # Get all shifts for the location view
            shifts = Shift.objects.filter(event=event, date=date)
            shifts_by_location = defaultdict(lambda: defaultdict(list))

            # Process each shift
            for s in shifts:
                start_hour = s.start_time.hour
                shift_start = s.start_time

                # Calculate grid positioning
                s.grid_row_start = start_hour + 1
                s.grid_row_span = max(1, (s.end_time.hour - s.start_time.hour) * 1)

                # Add to location's shifts
                shifts_by_location[s.location][start_hour].append(s)

            hour_slots = [{"hour": i} for i in range(24)]
            return render(
                request,
                "shifts/partials/location_columns.html",
                {
                    "shifts_by_location": shifts_by_location,
                    "locations": Location.objects.filter(event=event),
                    "hour_slots": hour_slots,
                    "current_event": event,
                    "current_date": date,
                },
            )
        else:
            # Get all shifts for the week view
            shifts = Shift.objects.filter(event=event, location=location)
            shifts_by_date = defaultdict(lambda: defaultdict(list))
            shift_groups = []

            # Process each shift
            for shift in shifts:
                start_hour = shift.start_time.hour
                shift_start = shift.start_time

                # Calculate grid positioning
                shift.grid_row_start = start_hour + 1
                shift.grid_row_span = max(
                    1, (shift.end_time.hour - shift.start_time.hour) * 1
                )

                # Find overlapping group or create new one
                added_to_group = False
                for group in shift_groups:
                    # Check if this shift overlaps with any shift in the group
                    overlaps = False
                    for existing_shift in group:
                        if (
                            shift_start < existing_shift.end_time
                            and shift.end_time > existing_shift.start_time
                        ):
                            overlaps = True
                            break

                    if overlaps:
                        group.append(shift)
                        added_to_group = True
                        # Update all shifts in this group to have same total_columns
                        total_columns = len(group)
                        for idx, s in enumerate(group):
                            s.column = idx  # Distribute shifts across columns
                            s.total_columns = total_columns
                        break

                if not added_to_group:
                    # Create new group for this shift
                    shift_groups.append([shift])
                    shift.column = 0
                    shift.total_columns = 1

                shifts_by_date[shift.date][start_hour].append(shift)

            # Generate hour slots
            hour_slots = [{"hour": i} for i in range(24)]

            return render(
                request,
                "shifts/partials/day_columns.html",
                {
                    "shifts_by_date": shifts_by_date,
                    "event_dates": event.get_dates(),
                    "hour_slots": hour_slots,
                    "current_event": event,
                    "selected_location": location,
                },
            )

    # Show the add modal
    event = get_object_or_404(Event, id=request.GET.get("event"))
    positions = Position.objects.all()
    locations = Location.objects.filter(event=event)

    # Get initial date and time from clicked cell
    date = request.GET.get("date")
    time = request.GET.get("time")

    # If time is provided, calculate a default end time 1 hour later
    end_time = None
    if time:
        try:
            start_dt = datetime.strptime(time, "%H:%M")
            end_dt = start_dt + timedelta(hours=1)
            end_time = end_dt.strftime("%H:%M")
        except ValueError:
            pass

    return render(
        request,
        "shifts/partials/add_shift_modal.html",
        {
            "positions": positions,
            "locations": locations,
            "start_time": time,
            "end_time": end_time,
            "date": date,
            "event": request.GET.get("event"),
            "location": request.GET.get("location"),
        },
    )


@login_required
def assign_volunteers_modal(request, shift_id):
    shift = get_object_or_404(Shift, id=shift_id)
    volunteers = ShiftVolunteer.objects.filter(shift=shift).select_related("volunteer")

    # Get volunteers who can work this position and aren't already assigned
    available_volunteers = (
        Volunteer.objects.filter(available_positions=shift.position, is_active=True)
        .exclude(
            id__in=ShiftVolunteer.objects.filter(shift=shift).values_list(
                "volunteer_id", flat=True
            )
        )
        .order_by("last_name", "first_name")
    )

    if request.method == "POST":
        volunteer_id = request.POST.get("volunteer")
        action = request.POST.get("action", "add")

        if action == "remove":
            # Remove volunteer from shift
            ShiftVolunteer.objects.filter(
                shift=shift, volunteer_id=volunteer_id
            ).delete()
        else:
            # Add volunteer to shift if not already at max
            if volunteers.count() < shift.max_volunteers:
                volunteer = get_object_or_404(Volunteer, id=volunteer_id)
                ShiftVolunteer.objects.create(
                    shift=shift, volunteer=volunteer, assigned_by=request.user
                )

        # Return the updated grid
        shifts = Shift.objects.filter(event=shift.event, date=shift.date)
        shifts_by_location = defaultdict(lambda: defaultdict(list))

        for s in shifts:
            start_hour = s.start_time.hour
            shift_start = s.start_time

            # Calculate grid positioning
            s.grid_row_start = start_hour + 1
            s.grid_row_span = max(1, (s.end_time.hour - s.start_time.hour) * 1)

            # Add to location's shifts
            shifts_by_location[s.location][start_hour].append(s)

        hour_slots = [{"hour": i} for i in range(24)]
        return render(
            request,
            "shifts/partials/day_columns.html",
            {
                "shifts_by_location": shifts_by_location,
                "locations": Location.objects.filter(event=shift.event),
                "hour_slots": hour_slots,
                "current_event": shift.event,
                "current_date": shift.date,
            },
        )

    return render(
        request,
        "shifts/partials/assign_volunteers_modal.html",
        {
            "shift": shift,
            "volunteers": volunteers,
            "available_volunteers": available_volunteers,
        },
    )


@login_required
def edit_shift_modal(request, shift_id):
    shift = get_object_or_404(Shift, id=shift_id)
    event = shift.event
    location = shift.location
    date = shift.date

    # Check if we're in day view or week view based on the referer and current URL
    referer = request.META.get("HTTP_REFERER", "")
    current_path = request.path
    is_day_view = "day/" in referer or "day/" in current_path

    if request.method == "DELETE":
        shift.delete()

        if is_day_view:
            # Get all shifts for the location view
            shifts = Shift.objects.filter(event=event, date=date)
            shifts_by_location = defaultdict(lambda: defaultdict(list))

            for s in shifts:
                start_hour = s.start_time.hour
                shift_start = s.start_time

                # Calculate grid positioning
                s.grid_row_start = start_hour + 1
                s.grid_row_span = max(1, (s.end_time.hour - s.start_time.hour) * 1)

                # Add to location's shifts
                shifts_by_location[s.location][start_hour].append(s)

            hour_slots = [{"hour": i} for i in range(24)]
            return render(
                request,
                "shifts/partials/location_columns.html",
                {
                    "shifts_by_location": shifts_by_location,
                    "locations": Location.objects.filter(event=event),
                    "hour_slots": hour_slots,
                    "current_event": event,
                    "current_date": date,
                },
            )
        else:
            shifts = Shift.objects.filter(event=event, location=location)
            shifts_by_date = defaultdict(lambda: defaultdict(list))
            shift_groups = []

            for s in shifts:
                start_hour = s.start_time.hour
                shift_start = s.start_time

                # Calculate grid positioning
                s.grid_row_start = start_hour + 1
                s.grid_row_span = max(1, (s.end_time.hour - s.start_time.hour) * 1)

                # Find overlapping group or create new one
                added_to_group = False
                for group in shift_groups:
                    # Check if this shift overlaps with any shift in the group
                    overlaps = False
                    for existing_shift in group:
                        if (
                            shift_start < existing_shift.end_time
                            and s.end_time > existing_shift.start_time
                        ):
                            overlaps = True
                            break

                    if overlaps:
                        group.append(s)
                        added_to_group = True
                        # Update all shifts in this group to have same total_columns
                        total_columns = len(group)
                        for idx, s in enumerate(group):
                            s.column = idx  # Distribute shifts across columns
                            s.total_columns = total_columns
                        break

                if not added_to_group:
                    # Create new group for this shift
                    shift_groups.append([s])
                    s.column = 0
                    s.total_columns = 1

                shifts_by_date[s.date][start_hour].append(s)

            hour_slots = [{"hour": i} for i in range(24)]
            return render(
                request,
                "shifts/partials/day_columns.html",
                {
                    "shifts_by_date": shifts_by_date,
                    "event_dates": event.get_dates(),
                    "hour_slots": hour_slots,
                    "current_event": event,
                    "selected_location": location,
                },
            )

    if request.method == "POST":
        # Handle both regular POST and PUT (via method override)
        is_put = request.headers.get("X-HTTP-Method-Override") == "PUT"
        if is_put or not request.headers.get("X-HTTP-Method-Override"):
            # Update the shift
            position = get_object_or_404(Position, id=request.POST.get("position"))
            location = get_object_or_404(Location, id=request.POST.get("location"))
            start_time = datetime.strptime(
                request.POST.get("start_time"), "%H:%M"
            ).time()
            end_time = datetime.strptime(request.POST.get("end_time"), "%H:%M").time()
            max_volunteers = int(request.POST.get("max_volunteers", 1))

            shift.position = position
            shift.location = location
            shift.start_time = start_time
            shift.end_time = end_time
            shift.max_volunteers = max_volunteers
            shift.save()

            if is_day_view:
                # Get all shifts for the location view
                shifts = Shift.objects.filter(event=event, date=date)
                shifts_by_location = defaultdict(lambda: defaultdict(list))

                for s in shifts:
                    start_hour = s.start_time.hour
                    shift_start = s.start_time

                    # Calculate grid positioning
                    s.grid_row_start = start_hour + 1
                    s.grid_row_span = max(1, (s.end_time.hour - s.start_time.hour) * 1)

                    # Add to location's shifts
                    shifts_by_location[s.location][start_hour].append(s)

                hour_slots = [{"hour": i} for i in range(24)]
                return render(
                    request,
                    "shifts/partials/location_columns.html",
                    {
                        "shifts_by_location": shifts_by_location,
                        "locations": Location.objects.filter(event=event),
                        "hour_slots": hour_slots,
                        "current_event": event,
                        "current_date": date,
                    },
                )
            else:
                # Return updated grid
                shifts = Shift.objects.filter(event=event, location=location)
                shifts_by_date = defaultdict(lambda: defaultdict(list))
                shift_groups = []

                for s in shifts:
                    start_hour = s.start_time.hour
                    shift_start = s.start_time

                    # Calculate grid positioning
                    s.grid_row_start = start_hour + 1
                    s.grid_row_span = max(1, (s.end_time.hour - s.start_time.hour) * 1)

                    # Find overlapping group or create new one
                    added_to_group = False
                    for group in shift_groups:
                        overlaps = False
                        for existing_shift in group:
                            if (
                                shift_start < existing_shift.end_time
                                and s.end_time > existing_shift.start_time
                            ):
                                overlaps = True
                                break

                        if overlaps:
                            group.append(s)
                            added_to_group = True
                            total_columns = len(group)
                            for idx, shift in enumerate(group):
                                shift.column = idx
                                shift.total_columns = total_columns
                            break

                    if not added_to_group:
                        shift_groups.append([s])
                        s.column = 0
                        s.total_columns = 1

                    shifts_by_date[s.date][start_hour].append(s)

                hour_slots = [{"hour": i} for i in range(24)]
                return render(
                    request,
                    "shifts/partials/day_columns.html",
                    {
                        "shifts_by_date": shifts_by_date,
                        "event_dates": event.get_dates(),
                        "hour_slots": hour_slots,
                        "current_event": event,
                        "selected_location": location,
                    },
                )

    # Show the edit modal
    positions = Position.objects.all()
    locations = Location.objects.filter(event=event)
    volunteers = ShiftVolunteer.objects.filter(shift=shift).select_related("volunteer")

    return render(
        request,
        "shifts/partials/edit_shift_modal.html",
        {
            "shift": shift,
            "positions": positions,
            "locations": locations,
            "volunteers": volunteers,
        },
    )


def send_shift_notifications(request, event, volunteers=None):
    """
    Send personalized email notifications to volunteers about their shifts.
    If volunteers is None, send to all volunteers with shifts in the event.
    """
    print(f"Starting send_shift_notifications for event {event} and volunteers {volunteers}")
    if volunteers is None:
        # Get all volunteers who have shifts in this event and haven't been notified
        volunteers = Volunteer.objects.filter(
            shifts__event=event,
            notification_email_sent=False
        ).distinct()

    errors = []
    for volunteer in volunteers:
        print(f"Processing volunteer {volunteer}")
        # Get all shifts for this volunteer in the event
        shifts = volunteer.shifts.filter(event=event).order_by('start_time')
        print(f"Found shifts: {shifts}")
        
        if not shifts.exists():
            print(f"No shifts found for volunteer {volunteer}")
            continue

        # Generate confirmation token
        print("Generating confirmation token")
        confirmation_token = volunteer.generate_confirmation_token()
        
        # Prepare email content
        context = {
            'volunteer': volunteer,
            'shifts': shifts,
            'event': event,
            'confirmation_url': request.build_absolute_uri(
                reverse('confirm_shifts', kwargs={'token': confirmation_token})
            )
        }
        print(f"Context prepared: {context}")
        
        try:
            print("Rendering email template")
            # Render HTML email template
            html_message = render_to_string('shifts/email/shift_notification.html', context)
            plain_message = strip_tags(html_message)
            print("Template rendered")
            
            print("Sending email")
            # Send email
            send_mail(
                subject=f'Your Shifts at {event.name}',
                message=plain_message,
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[volunteer.email],
                html_message=html_message,
                fail_silently=False,
            )
            print("Email sent")
            
            # Mark notification as sent
            volunteer.notification_email_sent = True
            volunteer.save(update_fields=['notification_email_sent'])
            print("Notification status updated")
        except Exception as e:
            import traceback
            print(f"Error sending email: {str(e)}")
            print(traceback.format_exc())
            errors.append(f"Error sending email to {volunteer.email}: {str(e)}")
            
    if errors:
        raise Exception("; ".join(errors))

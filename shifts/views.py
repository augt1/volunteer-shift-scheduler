from collections import defaultdict
from datetime import datetime, time, timedelta
from itertools import groupby
from operator import attrgetter

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.contrib.auth.models import User
from django.core.mail import send_mail
from django.http import HttpRequest, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.template.loader import render_to_string
from django.urls import reverse
from django.utils import timezone
from django.utils.html import strip_tags
import json

from events.models import Event
from volunteers.models import Volunteer

from .models import Location, Position, PositionVolunteer, Shift, ShiftVolunteer


def _generate_hour_slots(hour_start=6, hour_end=5):
    """Generate hour slots from 6am to 5am next day."""
    hour_slots = []
    for hour in range(hour_start, 24):  # 6am to 11:59pm
        hour_slots.append(time(hour, 0))
    for hour in range(0, hour_end):  # 12am to 5am next day
        hour_slots.append(time(hour, 0))

    return hour_slots


def _get_hour_position_mapping(hour_slots):
    """Create a mapping of hours to their position in the grid."""
    return {slot.hour: idx for idx, slot in enumerate(hour_slots)}


def _calculate_shift_grid_position(shift, hour_to_position):
    """Calculate grid positioning for a single shift."""
    start_hour = shift.start_time.hour
    start_minute = shift.start_time.minute
    end_hour = shift.end_time.hour
    end_minute = shift.end_time.minute
    
    # Handle shifts that cross midnight
    if shift.end_time < shift.start_time:
        end_hour += 24
    
    # Adjust for grid starting at 6am
    if start_hour < 6:
        start_hour += 24
    if end_hour < 6:
        end_hour += 24
    
    # Calculate grid positions
    shift.grid_row_start = hour_to_position[start_hour % 24] + 1
    
    # Calculate span including partial hours
    if end_minute > 0:
        # Add an extra hour if there are minutes in the end time
        shift.grid_row_span = (end_hour - start_hour) + (end_minute / 60)
    else:
        shift.grid_row_span = end_hour - start_hour
    
    return start_hour % 24


def _process_overlapping_shifts(shifts):
    """Process a list of shifts to detect overlaps and set column positions.

    Args:
        shifts: List of shifts to process

    Returns:
        None (shifts are modified in place)
    """
    if not shifts:
        return
        
    # Convert time objects to comparable values for overlap detection
    def get_comparable_times(shift):
        # Get the date from the shift
        shift_date = shift.date.date() if hasattr(shift.date, 'date') else shift.date
        
        # Create datetime objects for start and end
        start_dt = datetime.combine(shift_date, shift.start_time)
        end_dt = datetime.combine(shift_date, shift.end_time)
        
        # If end time is earlier than start time, it means the shift crosses midnight
        if shift.end_time < shift.start_time:
            end_dt += timedelta(days=1)
            
        return start_dt, end_dt
    
    # Create a list of shifts with their comparable times
    shifts_with_times = [(shift, *get_comparable_times(shift)) for shift in shifts]
    
    # Sort shifts by start time
    shifts_with_times.sort(key=lambda x: x[1])  # Sort by start_dt
    
    # Group overlapping shifts
    shift_groups = []
    
    for shift, start_dt, end_dt in shifts_with_times:
        # Try to find an existing group that this shift overlaps with
        added_to_group = False
        
        for group in shift_groups:
            # Check if this shift overlaps with any shift in the group
            overlaps = False
            
            for group_shift, group_start_dt, group_end_dt in group:
                # Two shifts overlap if one starts before the other ends
                if start_dt < group_end_dt and end_dt > group_start_dt:
                    overlaps = True
                    break
            
            if overlaps:
                group.append((shift, start_dt, end_dt))
                added_to_group = True
                break
        
        if not added_to_group:
            # Create a new group for this shift
            shift_groups.append([(shift, start_dt, end_dt)])
    
    # Update shift column information
    for group in shift_groups:
        total_columns = len(group)
        for idx, (shift, _, _) in enumerate(group):
            shift.column = idx
            shift.total_columns = total_columns


def _process_shifts_for_week_view(shifts, hour_to_position):
    """Process shifts and calculate their grid positions.

    Args:
        shifts: QuerySet of shifts to process
        hour_to_position: Mapping of hours to grid positions

    Returns:
        shifts_by_date: Dictionary of shifts organized by date and hour
    """
    # First, organize shifts by date
    shifts_by_date_dict = defaultdict(list)
    for shift in shifts:
        # Convert date to datetime.date for consistent key lookup
        shift_date = shift.date.date() if hasattr(shift.date, "date") else shift.date
        
        # Always add the shift to its start date, even if it crosses midnight
        shifts_by_date_dict[shift_date].append(shift)

    # Process each date's shifts separately
    result = {}
    for date, date_shifts in shifts_by_date_dict.items():
        # Calculate grid positions for all shifts on this date
        for shift in date_shifts:
            _calculate_shift_grid_position(shift, hour_to_position)

        # Process overlapping shifts for this date
        _process_overlapping_shifts(date_shifts)

        # Organize shifts by hour for template rendering
        shifts_by_hour = defaultdict(list)
        for shift in date_shifts:
            # Convert start_hour to time object for template rendering
            hour_time = time(shift.start_time.hour, 0)
            shifts_by_hour[hour_time].append(shift)

        # Convert hour keys to string format for template
        hour_shifts_str = {}
        for hour_key, hour_shifts in shifts_by_hour.items():
            hour_str = hour_key.strftime("%H:%M")
            hour_shifts_str[hour_str] = hour_shifts

        # Add to result with date as string key
        result[date.isoformat()] = hour_shifts_str

    return result


def _process_shifts_for_day_view(shifts, hour_to_position):
    """Process shifts for day view, organizing them by location.

    Args:
        shifts: QuerySet of shifts to process
        hour_to_position: Mapping of hours to grid positions

    Returns:
        shifts_by_location: Dictionary of shifts organized by location and hour
    """
    # Create a dictionary with location objects as keys and shifts organized by hour as values
    shifts_by_location = {}

    # First, organize shifts by location
    location_shifts_dict = defaultdict(list)
    for shift in shifts:
        # For shifts that cross midnight, we still want them to appear in their start day
        location_shifts_dict[shift.location].append(shift)

    # Then process each location's shifts
    for location, location_shifts in location_shifts_dict.items():
        # Calculate grid positions for all shifts at this location
        for shift in location_shifts:
            _calculate_shift_grid_position(shift, hour_to_position)

        # Process overlapping shifts for this location
        _process_overlapping_shifts(location_shifts)

        # Organize shifts by hour for template rendering
        shifts_by_hour = defaultdict(list)
        for shift in location_shifts:
            # Convert hour to string format for template
            hour_str = shift.start_time.strftime("%H:%M")
            shifts_by_hour[hour_str].append(shift)

        # Store the processed shifts with the location as key
        shifts_by_location[location] = dict(shifts_by_hour)

    return shifts_by_location


def _enhance_volunteers_with_stats(volunteers, event):
    """
    Enhance volunteer objects with shift count and total hours for a specific event.
    """
    for volunteer in volunteers:
        # Get all shifts for this volunteer in this event
        volunteer_shifts = ShiftVolunteer.objects.filter(
            volunteer=volunteer,
            shift__event=event
        ).select_related('shift')
        
        # Calculate total shifts and hours
        volunteer.shift_count = volunteer_shifts.count()
        
        total_hours = 0
        for vs in volunteer_shifts:
            # Calculate hours for each shift
            start_time = vs.shift.start_time
            end_time = vs.shift.end_time
            
            # Handle shifts that cross midnight
            if end_time < start_time:
                end_time_hours = end_time.hour + 24
            else:
                end_time_hours = end_time.hour
                
            hours = end_time_hours - start_time.hour
            minutes = end_time.minute - start_time.minute
            
            total_hours += hours + (minutes / 60)
            
        volunteer.total_hours = round(total_hours, 1)
    
    return volunteers


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

    hour_slots = _generate_hour_slots()
    hour_to_position = _get_hour_position_mapping(hour_slots)

    # Get all shifts for the selected location with improved prefetching
    shifts = (
        Shift.objects.filter(event=current_event, location=selected_location)
        .select_related("position", "location")
        .prefetch_related(
            "volunteers",
            "shiftvolunteer_set",
            "shiftvolunteer_set__volunteer",
        )
    )

    shifts_by_date = _process_shifts_for_week_view(shifts, hour_to_position)

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

    hour_slots = _generate_hour_slots()
    hour_to_position = _get_hour_position_mapping(hour_slots)

    # Get all locations for this event
    locations = Location.objects.filter(event=current_event)

    # Get all shifts for the current date with improved prefetching
    shifts = (
        Shift.objects.filter(date=current_date, event=current_event)
        .select_related("position", "location")
        .prefetch_related(
            "volunteers",
            "shiftvolunteer_set",
            "shiftvolunteer_set__volunteer",
        )
    )

    # Process shifts by location
    shifts_by_location = _process_shifts_for_day_view(shifts, hour_to_position)

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

        hour_slots = _generate_hour_slots()
        hour_to_position = _get_hour_position_mapping(hour_slots)

        if is_day_view:
            # Get all shifts for the location view
            shifts = (
                Shift.objects.filter(event=event, date=date)
                .select_related("position", "location")
                .prefetch_related("volunteers")
            )
            shifts_by_location = _process_shifts_for_day_view(shifts, hour_to_position)

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
            shifts = (
                Shift.objects.filter(event=event, location=location)
                .select_related("position")
                .prefetch_related("volunteers")
            )
            shifts_by_date = _process_shifts_for_week_view(shifts, hour_to_position)

            return render(
                request,
                "shifts/partials/day_columns.html",
                {
                    "current_event": event,
                    "event_dates": event.get_dates(),
                    "shifts_by_date": shifts_by_date,
                    "hour_slots": hour_slots,
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
    #TODO: modal doens refresh the week grid when closing
    
    # Get source from request parameters (GET, POST, or HTMX vals)
    source = request.GET.get("source", None)
    if not source and request.method == "POST":
        # Try to get from POST data or HTMX vals
        source = request.POST.get("source", None)
        if not source and request.headers.get("HX-Trigger-Name") == "hx-vals":
            # This is from hx-vals
            try:
                import json
                body = json.loads(request.body.decode("utf-8"))
                source = body.get("source", "day")
            except:
                source = "day"
    
    if not source:
        source = "day"  # Default to day view
    
    print(f"Source: {source}")

    # Get volunteers who can work this position and aren't already assigned
    available_volunteers = (
        Volunteer.objects.filter(available_positions=shift.position, is_active=True)
        .exclude(
            id__in=ShiftVolunteer.objects.filter(shift=shift).values_list(
                "volunteer_id", flat=True
            )
        )
        .order_by("first_name", "last_name")
    )
    
    available_volunteers = _enhance_volunteers_with_stats(available_volunteers, shift.event)
    
    if request.method == "POST":
        # Try to get action and volunteer from POST data or HTMX vals
        action = request.POST.get("action", None)
        volunteer_ids = request.POST.getlist("volunteer")
        
        # If not in POST, try to get from HTMX vals
        if (not action or not volunteer_ids) and request.headers.get("HX-Trigger-Name") == "hx-vals":
            try:
                import json
                body = json.loads(request.body.decode("utf-8"))
                action = body.get("action", "add")
                volunteer_id = body.get("volunteer")
                if volunteer_id:
                    volunteer_ids = [volunteer_id]
                else:
                    volunteer_ids = []
            except:
                action = "add"
                volunteer_ids = []
        
        if not action:
            action = "add"  # Default action

        if action == "remove" and volunteer_ids:
            # Remove volunteer from shift
            ShiftVolunteer.objects.filter(
                shift=shift, volunteer_id=volunteer_ids[0]
            ).delete()
        elif action == "close":
            # Return the updated grid based on the source
            hour_slots = _generate_hour_slots()
            hour_to_position = _get_hour_position_mapping(hour_slots)
            
            if source == "week":
                # For week view
                start_date = shift.date - timedelta(days=shift.date.weekday())
                end_date = start_date + timedelta(days=6)
                
                # Get all dates in the week using event.get_dates()
                event_dates = shift.event.get_dates()
                # Filter to only include dates in the current week
                event_dates = [date for date in event_dates if start_date <= date <= end_date]
                
                # Get shifts for the week
                week_shifts = (
                    Shift.objects.filter(
                        event=shift.event, 
                        date__gte=start_date, 
                        date__lte=end_date
                    )
                    .select_related("position", "location")
                    .prefetch_related("volunteers")
                )
                
                # Process shifts by date
                shifts_by_date = {}
                for date in event_dates:
                    day_shifts = week_shifts.filter(date=date)
                    date_str = date.strftime('%Y-%m-%d')
                    shifts_by_date[date_str] = _process_shifts_for_day_view(
                        day_shifts, hour_to_position
                    )
                
                # Return the updated grid
                return render(
                    request,
                    "shifts/partials/day_columns.html",
                    {
                        "event_dates": event_dates,
                        "shifts_by_date": shifts_by_date,
                        "locations": Location.objects.filter(event=shift.event),
                        "hour_slots": hour_slots,
                        "current_event": shift.event,
                        "selected_location": None,  # We're showing all locations
                    },
                )
            else:
                # For day view
                # Get all shifts for the location view
                shifts = (
                    Shift.objects.filter(event=shift.event, date=shift.date)
                    .select_related("position", "location")
                    .prefetch_related("volunteers")
                )
                shifts_by_location = _process_shifts_for_day_view(shifts, hour_to_position)
                
                # Return the updated grid
                return render(
                    request,
                    "shifts/partials/location_columns.html",
                    {
                        "shifts_by_location": shifts_by_location,
                        "locations": Location.objects.filter(event=shift.event),
                        "hour_slots": hour_slots,
                        "current_event": shift.event,
                        "current_date": shift.date,
                    },
                )
        else:
            # Add the volunteer to the shift if not already at max
            if volunteers.count() < shift.max_volunteers and volunteer_ids:
                volunteer_id = volunteer_ids[0]  # We're now handling one volunteer at a time
                if volunteer_id:
                    volunteer = get_object_or_404(Volunteer, id=volunteer_id)
                    # Check if this volunteer is already assigned to avoid duplicates
                    if not ShiftVolunteer.objects.filter(shift=shift, volunteer=volunteer).exists():
                        ShiftVolunteer.objects.create(
                            shift=shift, volunteer=volunteer, assigned_by=request.user
                        )

        # Refresh the volunteer lists
        volunteers = ShiftVolunteer.objects.filter(shift=shift).select_related("volunteer")
        available_volunteers = (
            Volunteer.objects.filter(available_positions=shift.position, is_active=True)
            .exclude(
                id__in=ShiftVolunteer.objects.filter(shift=shift).values_list(
                    "volunteer_id", flat=True
                )
            )
            .order_by("first_name", "last_name")
        )
        
        available_volunteers = _enhance_volunteers_with_stats(available_volunteers, shift.event)
        
        # Return the updated modal with refreshed volunteer lists
        return render(
            request,
            "shifts/partials/assign_volunteers_modal.html",
            {
                "shift": shift,
                "volunteers": volunteers,
                "available_volunteers": available_volunteers,
                "source": source,
            },
        )

    # Return the modal
    return render(
        request,
        "shifts/partials/assign_volunteers_modal.html",
        {
            "shift": shift,
            "volunteers": volunteers,
            "available_volunteers": available_volunteers,
            "source": source,
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
            shifts_by_location = _process_shifts_for_day_view(
                shifts, _get_hour_position_mapping(_generate_hour_slots())
            )

            hour_slots = _generate_hour_slots()
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
            shifts_by_date = _process_shifts_for_week_view(
                shifts,
                _get_hour_position_mapping(_generate_hour_slots()),
            )

            hour_slots = _generate_hour_slots()
            return render(
                request,
                "shifts/partials/day_columns.html",
                {
                    "current_event": event,
                    "event_dates": event.get_dates(),
                    "shifts_by_date": shifts_by_date,
                    "hour_slots": hour_slots,
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
            start_time = datetime.strptime(request.POST.get("start_time"), "%H:%M").time()
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
                shifts_by_location = _process_shifts_for_day_view(
                    shifts, _get_hour_position_mapping(_generate_hour_slots())
                )

                hour_slots = _generate_hour_slots()
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
                shifts_by_date = _process_shifts_for_week_view(
                    shifts,
                    _get_hour_position_mapping(_generate_hour_slots()),
                )

                hour_slots = _generate_hour_slots()
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
    print(
        f"Starting send_shift_notifications for event {event} and volunteers {volunteers}"
    )
    if volunteers is None:
        # Get all volunteers who have shifts in this event and haven't been notified
        volunteers = Volunteer.objects.filter(
            shifts__event=event, notification_email_sent=False
        ).distinct()

    errors = []
    for volunteer in volunteers:
        print(f"Processing volunteer {volunteer}")
        # Get all shifts for this volunteer in the event
        shifts = volunteer.shifts.filter(event=event).order_by("start_time")
        print(f"Found shifts: {shifts}")

        if not shifts.exists():
            print(f"No shifts found for volunteer {volunteer}")
            continue

        # Generate confirmation token
        print("Generating confirmation token")
        confirmation_token = volunteer.generate_confirmation_token()

        # Prepare email content
        context = {
            "volunteer": volunteer,
            "shifts": shifts,
            "event": event,
            "confirmation_url": request.build_absolute_uri(
                reverse("confirm_shifts", kwargs={"token": confirmation_token})
            ),
        }
        print(f"Context prepared: {context}")

        try:
            print("Rendering email template")
            # Render HTML email template
            html_message = render_to_string(
                "shifts/email/shift_notification.html", context
            )
            plain_message = strip_tags(html_message)
            print("Template rendered")

            print("Sending email")
            # Send email
            send_mail(
                subject=f"Your Shifts at {event.name}",
                message=plain_message,
                from_email=f"Athens Rhythm Hop <{settings.EMAIL_HOST_USER}>",
                recipient_list=[volunteer.email],
                html_message=html_message,
                fail_silently=False,
            )
            print("Email sent")

            # Mark notification as sent
            volunteer.notification_email_sent = True
            volunteer.save(update_fields=["notification_email_sent"])
            print("Notification status updated")
        except Exception as e:
            import traceback

            print(f"Error sending email: {str(e)}")
            print(traceback.format_exc())
            errors.append(f"Error sending email to {volunteer.email}: {str(e)}")

    if errors:
        raise Exception("; ".join(errors))

from datetime import datetime, timedelta

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db.models import Count, F, FloatField, Max, Min, Q, Sum
from django.db.models.functions import Coalesce, ExtractHour, ExtractMinute
from django.http import HttpResponse, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.csrf import csrf_protect
from django.views.decorators.http import require_http_methods

from events.models import Event
from shifts.models import Position, Shift, ShiftVolunteer

from .forms import VolunteerForm
from .models import Volunteer

# Create your views here.


@login_required
def volunteer_list(request):
    # Get filters from request
    search_query = request.GET.get("search", "").strip()
    position_filter = request.GET.get("position", "")
    status_filter = request.GET.get("status", "")

    # Base queryset
    volunteers = Volunteer.objects.all()

    # Apply search filter
    if search_query:
        volunteers = volunteers.filter(
            Q(first_name__icontains=search_query)
            | Q(last_name__icontains=search_query)
            | Q(email__icontains=search_query)
            | Q(phone_number__icontains=search_query)
        )

    # Apply position filter
    if position_filter:
        volunteers = volunteers.filter(available_positions__id=position_filter)

    # Apply status filter
    if status_filter:
        if status_filter == "active":
            volunteers = volunteers.filter(is_active=True)
        elif status_filter == "inactive":
            volunteers = volunteers.filter(is_active=False)
        elif status_filter == "assigned":
            volunteers = volunteers.filter(available_positions__isnull=False).distinct()
        elif status_filter == "unassigned":
            volunteers = volunteers.filter(available_positions__isnull=True)

    # Get total volunteers and status counts
    total_volunteers = Volunteer.objects.count()
    active_volunteers = Volunteer.objects.filter(is_active=True).count()
    assigned_volunteers = (
        Volunteer.objects.filter(available_positions__isnull=False).distinct().count()
    )
    unassigned_volunteers = Volunteer.objects.filter(
        available_positions__isnull=True
    ).count()
    confirmed_volunteers = Volunteer.objects.filter(has_confirmed=True).count()

    # Get position stats
    position_stats = Position.objects.annotate(
        volunteer_count=Count("volunteers"),
        confirmed_count=Count("volunteers", filter=Q(volunteers__has_confirmed=True))
    ).values("id", "name", "color", "volunteer_count", "confirmed_count")

    # Add annotations to filtered queryset
    volunteers = volunteers.annotate(
        total_shifts=Count("shifts"),
        total_hours=Sum(
            (
                ExtractHour("shifts__end_time") * 60
                + ExtractMinute("shifts__end_time")
                - ExtractHour("shifts__start_time") * 60
                - ExtractMinute("shifts__start_time")
            )
            / 60.0,
            output_field=FloatField(),
        ),
    ).order_by("first_name", "last_name")

    return render(
        request,
        "volunteers/volunteer_list.html",
        {
            "volunteers": volunteers,
            "total_volunteers": total_volunteers,
            "active_volunteers": active_volunteers,
            "assigned_volunteers": assigned_volunteers,
            "unassigned_volunteers": unassigned_volunteers,
            "confirmed_volunteers": confirmed_volunteers,
            "position_stats": position_stats,
            "positions": Position.objects.all(),
            "search_query": search_query,
            "position_filter": position_filter,
            "status_filter": status_filter,
        },
    )


@login_required
def volunteer_create(request):
    if request.method == "POST":
        form = VolunteerForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Volunteer created successfully.")
            return redirect("volunteer_list")
    else:
        form = VolunteerForm()

    return render(
        request,
        "volunteers/volunteer_form.html",
        {"form": form, "title": "Create Volunteer"},
    )


@login_required
def volunteer_update(request, pk):
    volunteer = get_object_or_404(Volunteer, pk=pk)
    if request.method == "POST":
        form = VolunteerForm(request.POST, instance=volunteer)
        if form.is_valid():
            form.save()
            messages.success(request, "Volunteer updated successfully.")
            return redirect("volunteer_list")
    else:
        form = VolunteerForm(instance=volunteer)

    return render(
        request,
        "volunteers/volunteer_form.html",
        {"form": form, "title": "Update Volunteer"},
    )


@login_required
def volunteer_delete(request, pk):
    volunteer = get_object_or_404(Volunteer, pk=pk)
    if request.method == "POST" or request.method == "DELETE":
        volunteer.delete()
        messages.success(request, "Volunteer deleted successfully.")

        # If it's an HTMX request, return an empty response to remove the row
        if request.headers.get("HX-Request"):
            return HttpResponse("")

        return redirect("volunteer_list")

    return render(
        request, "volunteers/volunteer_confirm_delete.html", {"volunteer": volunteer}
    )


@login_required
def update_volunteer_positions(request, pk):
    volunteer = get_object_or_404(Volunteer, pk=pk)
    if request.method == "POST":
        position_ids = request.POST.getlist("positions")
        volunteer.available_positions.set(position_ids)
        return render(
            request,
            "volunteers/partials/volunteer_positions.html",
            {"volunteer": volunteer, "positions": Position.objects.all()},
        )

    return render(
        request,
        "volunteers/partials/position_modal.html",
        {"volunteer": volunteer, "positions": Position.objects.all()},
    )


@login_required
def volunteer_schedule(request):
    # Get all events to find the date range
    events = Event.objects.all()
    if events.exists():
        # Get the min and max dates from events
        event_range = events.aggregate(start=Min("start_date"), end=Max("end_date"))

        # Generate all dates between start and end
        current_date = event_range["start"]
        event_dates = []
        while current_date <= event_range["end"]:
            event_dates.append(current_date)
            current_date += timedelta(days=1)
    else:
        event_dates = []

    # Get active volunteers with their shifts and stats
    volunteers = (
        Volunteer.objects.filter(is_active=True)
        .prefetch_related("shifts")
        .annotate(
            shift_count=Count("shifts"),
            total_hours=Sum(
                (
                    ExtractHour("shifts__end_time") * 60
                    + ExtractMinute("shifts__end_time")
                    - ExtractHour("shifts__start_time") * 60
                    - ExtractMinute("shifts__start_time")
                )
                / 60.0,
                output_field=FloatField(),
                default=0,
            ),
        )
        .order_by("first_name", "last_name")
    )

    # Create a lookup of shifts by volunteer and date
    shifts_by_volunteer = {}
    for volunteer in volunteers:
        shifts_by_volunteer[volunteer.id] = {
            date: list(volunteer.shifts.filter(date=date).order_by("start_time"))
            for date in event_dates
        }

    return render(
        request,
        "volunteers/volunteer_schedule.html",
        {
            "volunteers": volunteers,
            "days": event_dates,
            "shifts_by_volunteer": shifts_by_volunteer,
        },
    )


@login_required
@csrf_protect
@require_http_methods(["POST"])
def send_volunteer_notification(request, volunteer_id):
    """Send shift notification email to a specific volunteer."""
    try:
        print(f"Starting send_volunteer_notification for volunteer {volunteer_id}")
        volunteer = get_object_or_404(Volunteer, pk=volunteer_id)
        event = Event.objects.filter(end_date__gte=timezone.now()).first()

        print(f"Found event: {event}")
        if not event:
            return JsonResponse({"status": "error", "message": "No active event found"})

        # Check if volunteer has any shifts in this event
        has_shifts = volunteer.shifts.filter(event=event).exists()
        print(f"Volunteer has shifts: {has_shifts}")
        if not has_shifts:
            return JsonResponse(
                {
                    "status": "error",
                    "message": "No shifts found for this volunteer in the current event",
                }
            )

        print("Importing send_shift_notifications")
        from shifts.views import send_shift_notifications

        print("Calling send_shift_notifications")
        send_shift_notifications(request, event, volunteers=[volunteer])
        print("Email sent successfully")

        return JsonResponse({"status": "success"})
    except Exception as e:
        import traceback

        print(f"Error in send_volunteer_notification: {str(e)}")
        print(traceback.format_exc())
        return JsonResponse({"status": "error", "message": str(e)}, status=500)


def confirm_shifts(request, token):
    """Handle volunteer shift confirmation via email link."""
    try:
        volunteer = get_object_or_404(Volunteer, confirmation_token=token)

        if not volunteer.has_confirmed:
            volunteer.has_confirmed = True
            volunteer.save(update_fields=["has_confirmed"])
            messages.success(request, "Thank you for confirming your shifts!")
        else:
            messages.info(request, "You have already confirmed your shifts.")

        return redirect("confirmation_thank_you")
    except Exception as e:
        messages.error(request, "Invalid confirmation link.")
        return redirect("week_view")


def confirmation_thank_you(request):
    """Show thank you page after confirming shifts."""
    return render(request, "volunteers/confirmation_thank_you.html")

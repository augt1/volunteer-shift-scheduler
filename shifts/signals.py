from django.db.models.signals import post_save, post_delete, m2m_changed
from django.dispatch import receiver
from .models import ShiftVolunteer, Shift

@receiver(post_save, sender=ShiftVolunteer)
@receiver(post_delete, sender=ShiftVolunteer)
def reset_notification_status(sender, instance, **kwargs):
    """Reset notification_email_sent and has_confirmed when a volunteer's shifts change."""
    if instance.volunteer:
        instance.volunteer.notification_email_sent = False
        instance.volunteer.has_confirmed = False
        instance.volunteer.save(update_fields=['notification_email_sent', 'has_confirmed'])

@receiver(m2m_changed, sender=Shift.volunteers.through)
def handle_shift_changes(sender, instance, action, pk_set, **kwargs):
    """Reset notification status when volunteers are added or removed from a shift."""
    if action in ["post_add", "post_remove", "post_clear"]:
        # Get all affected volunteers
        from volunteers.models import Volunteer
        affected_volunteers = Volunteer.objects.filter(pk__in=pk_set) if pk_set else instance.volunteers.all()
        
        # Reset notification status and confirmation for all affected volunteers
        affected_volunteers.update(notification_email_sent=False, has_confirmed=False)

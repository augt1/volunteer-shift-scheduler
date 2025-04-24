from django.db import models
from django.core.validators import RegexValidator
from django.utils.crypto import get_random_string

# Create your models here.

class Volunteer(models.Model):
    first_name = models.CharField(max_length=30)
    last_name = models.CharField(max_length=30)
    email = models.EmailField(unique=True)
    phone_regex = RegexValidator(
        regex=r'^\+?1?\d{9,15}$',
        message="Phone number must be entered in the format: '+999999999'. Up to 15 digits allowed."
    )
    phone_number = models.CharField(validators=[phone_regex], max_length=17, blank=True)
    notification_email_sent = models.BooleanField(default=False)
    has_confirmed = models.BooleanField(default=False)
    confirmation_token = models.CharField(max_length=64, blank=True)
    notes = models.TextField(blank=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    def __str__(self):
        return f"{self.first_name} {self.last_name}"
    
    def get_full_name(self):
        return f"{self.first_name} {self.last_name}"

    def generate_confirmation_token(self):
        self.confirmation_token = get_random_string(64)
        self.save(update_fields=['confirmation_token'])
        return self.confirmation_token

    class Meta:
        ordering = ['first_name', 'last_name']
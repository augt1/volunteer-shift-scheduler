from django.urls import path
from . import views

urlpatterns = [
    path('volunteers/', views.volunteer_list, name='volunteer_list'),
    path('volunteers/create/', views.volunteer_create, name='volunteer_create'),
    path('volunteers/<int:pk>/', views.volunteer_update, name='volunteer_update'),
    path('volunteers/<int:pk>/delete/', views.volunteer_delete, name='volunteer_delete'),
    path('volunteers/<int:volunteer_id>/send-notification/', views.send_volunteer_notification, name='send_volunteer_notification'),
    path('volunteers/confirm/<str:token>/', views.confirm_shifts, name='confirm_shifts'),
    path('volunteers/thank-you/', views.confirmation_thank_you, name='confirmation_thank_you'),
    path('schedule/', views.volunteer_schedule, name='volunteer_schedule'),
    path('update-positions/<int:pk>/', views.update_volunteer_positions, name='update_volunteer_positions'),
]

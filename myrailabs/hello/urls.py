"""
Myrai Labs - URL Configuration
"""

from django.urls import path

from . import views

urlpatterns = [
    path("", views.index, name="index"),
    path("about/", views.about, name="about"),
    path("services/", views.services, name="services"),
    path("contact/", views.contact, name="contact"),

    path("auth/register/", views.register, name="register"),
    path("auth/login/", views.login_view, name="login"),
    path("auth/logout/", views.logout_view, name="logout"),

    path("quote/", views.request_quote, name="request_quote"),
    path("quote/service/<slug:service_slug>/", views.request_quote, name="request_quote_service"),
    path("quote/thanks/<str:ref>/", views.quote_submitted, name="quote_submitted"),
    path("quote/status/", views.quote_status, name="quote_status"),
    path("whatsapp/webhook/", views.whatsapp_webhook, name="whatsapp_webhook"),
]
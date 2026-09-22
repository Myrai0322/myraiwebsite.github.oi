"""
Myrai Labs - Context Strings
"""
from django.conf import settings

from .whatsapp import wa_me_link


def site_settings(request):
    default_msg = f"Hi {settings.BUSINESS_NAME}! I'd like to chat about a project."
    return {
        "BUSINESS": {
            "name": settings.BUSINESS_NAME,
            "tagline": settings.BUSINESS_TAGLINE,
            "phone": settings.BUSINESS_PHONE,
            "email": settings.BUSINESS_EMAIL,
            "location": settings.BUSINESS_LOCATION,
        },
        "WHATSAPP_NUMBER": settings.WHATSAPP_NUMBER,
        "wa_float": wa_me_link(default_msg),
        "wa_footer": wa_me_link(default_msg),
    }
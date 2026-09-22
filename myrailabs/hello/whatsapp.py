"""
Myrai Labs - WhatsApp Integration
"""
import logging
import re
import threading
import urllib.parse
import urllib.request

from django.conf import settings

from .models import WhatsAppOutbox

logger = logging.getLogger(__name__)


# THE CLICK TO CHAT DEEP LINKS
def normalise_sa_number(number):
    """'078 233 9131' / '+27 78 233 9131' -> '27782339131'."""
    digits = re.sub(r"\D", "", str(number))
    if digits.startswith("0"):
        return "27" + digits[1:]
    if digits.startswith("27"):
        return digits
    return digits


def wa_me_link(message="", phone=None):
    """Public click-to-chat URL targeting the business WhatsApp number."""
    number = normalise_sa_number(phone or settings.WHATSAPP_NUMBER)
    url = f"https://wa.me/{number}"
    if message:
        url += "?text=" + urllib.parse.quote(message)
    return url


def wa_service_link(service_name):
    """Prefilled message for a specific service's CTA button."""
    return wa_me_link(
        f"Hi {settings.BUSINESS_NAME}! I'm interested in *{service_name}*. "
        "Can you help me with that?"
    )


# OUTBOUND API CLOUD ALERTS
def _cloud_api_send(to, body):
    """Blocking Meta Cloud API call. Returns (ok, response_text)."""
    version = settings.WHATSAPP_API_VERSION
    url = f"https://graph.facebook.com/{version}/{settings.WHATSAPP_PHONE_ID}/messages"
    payload = urllib.parse.urlencode({
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text[body]": body[:4000],
    }).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        method="POST",
        headers={
            "Authorization": f"Bearer {settings.WHATSAPP_TOKEN}",
            "Content-Type": "application/x-www-form-urlencoded",
        },
    )
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            return True, resp.read().decode("utf-8", "replace")[:2000]
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"[:2000]


def _deliver(outbox_id, to, body, related_ref):
    """Runs on a worker thread: send, then persist the outcome. Never raises."""
    try:
        from .models import WhatsAppOutbox as Outbox

        if settings.WHATSAPP_ENABLED and settings.WHATSAPP_PHONE_ID and settings.WHATSAPP_TOKEN:
            ok, response = _cloud_api_send(to, body)
            status = Outbox.Status.SENT if ok else Outbox.Status.FAILED
            if not ok:
                logger.warning("WhatsApp alert failed (%s): %s", related_ref, response)
        else:
            response = "Queued: WhatsApp not configured (WHATSAPP_ENABLED/PHONE_ID/TOKEN)"
            status = Outbox.Status.PENDING

        Outbox.objects.filter(pk=outbox_id).update(
            status=status, provider_response=response
        )
    except Exception:
        logger.exception("WhatsApp delivery thread crashed (%s)", related_ref)


def send_whatsapp(body, to=None, related_ref=""):
    """Log an outbox row, then deliver on a daemon thread. Never raises."""
    to = normalise_sa_number(to or settings.WHATSAPP_ALERT_TO)
    try:
        row = WhatsAppOutbox.objects.create(to=to, body=body[:4000], related_ref=related_ref)
        thread = threading.Thread(
            target=_deliver, args=(row.pk, to, body[:4000], related_ref), daemon=True
        )
        thread.start()
        return row
    except Exception:
        logger.exception("WhatsApp outbox write failed (%s)", related_ref)
        return None


def notify_new_quote(quote):
    """Owner alert the moment a quote request lands."""
    deadline = quote.display_deadline
    budget = f"R{quote.budget:,.0f}" if quote.budget else "Not stated"
    body = (
        f"*New quote request — {quote.ref}*\n"
        f"Service: {quote.service.name} ({quote.service.price_display})\n"
        f"Client: {quote.name}\n"
        f"Email: {quote.email}\n"
        f"Phone: {quote.phone or 'not provided'}\n"
        f"Deadline: {deadline}\n"
        f"Budget: {budget}\n"
        f"WhatsApp updates: {'yes' if quote.contact_via_whatsapp else 'no'}\n"
        f"Open admin to respond."
    )
    return send_whatsapp(body, related_ref=quote.ref)


def notify_status_change(quote):
    """Opt-in WhatsApp update to the client when their order status changes."""
    if not quote.contact_via_whatsapp or not quote.phone:
        return None
    body = (
        f"Hi {quote.name}! Your {settings.BUSINESS_NAME} order *{quote.ref}* "
        f"({quote.service.name}) is now: *{quote.get_status_display()}*.\n"
        f"Questions? Just reply here."
    )
    return send_whatsapp(body, to=quote.phone, related_ref=quote.ref)


def notify_contact_message(contact):
    body = (
        f"*New website message*\n"
        f"From: {contact.name} <{contact.email}>\n"
        f"{contact.message[:800]}"
    )
    return send_whatsapp(body, related_ref="CONTACT")
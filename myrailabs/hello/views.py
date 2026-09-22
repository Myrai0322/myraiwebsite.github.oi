"""
Myrai Labs - The Views
"""
import json
import logging

from django.contrib import messages
from django.conf import settings
from django.contrib.auth import authenticate
from django.contrib.auth import login as auth_login
from django.contrib.auth import logout as auth_logout
from django.contrib.auth.decorators import login_required
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.core.mail import mail_admins
from django.http import HttpResponse
from django.db import IntegrityError
from django.shortcuts import get_object_or_404, redirect, render

from .forms import ContactForm, CustomUserForm, QuoteRequestForm, QuoteStatusLookupForm
from .models import ContactMessage, QuoteRequest, Service, ServiceCategory
from .utils import too_many_requests
from .whatsapp import notify_contact_message, notify_new_quote, wa_me_link

logger = logging.getLogger(__name__)

def index(request):
    featured = (
        Service.objects.filter(featured=True, is_active=True)
        .select_related("category")[:4]
    )
    counts = {
        c.slug.replace("-", "_"): c.services.count()
        for c in ServiceCategory.objects.filter(is_active=True)
    }
    return render(request, "myrai/index.html", {
        "featured_services": featured,
        "category_counts": counts,
    })


def about(request):
    return render(request, "myrai/about.html")


def services(request):
    cats = (
        ServiceCategory.objects.filter(is_active=True)
        .prefetch_related("services")
    )
    return render(request, "myrai/services.html", {"categories": cats})


# THE AUTH
def register(request):
    if request.user.is_authenticated:
        return redirect("index")
    if request.method == "POST":
        form = CustomUserForm(request.POST)
        if form.is_valid():
            try:
                user = form.save()
                auth_login(request, user)
                messages.success(request, "Welcome to Myrai Labs — you're registered and signed in!")
                return redirect("index")
            except IntegrityError:
                form.add_error("username", "That username is taken — try another.")
        else:
            messages.error(request, "Please fix the errors below.")
    else:
        form = CustomUserForm()
    return render(request, "myrai/register.html", {"form": form})


def login_view(request):
    if request.user.is_authenticated:
        return redirect("index")
    if request.method == "POST":
        username = (request.POST.get("username") or "").strip()
        password = request.POST.get("password") or ""
        user = authenticate(request, username=username, password=password)
        if user is not None:
            auth_login(request, user)
            messages.success(request, f"Welcome back, {user.username}!")
            return redirect(request.GET.get("next") or "index")
        messages.error(request, "Wrong username or password — try logging in again.")
    return render(request, "myrai/login.html")


@login_required
def logout_view(request):
    if request.method == "POST":
        auth_logout(request)
        messages.info(request, "Signed out. See you soon!")
        return redirect("index")
    return redirect("index")


# THE QUOTE PIPELINE
def request_quote(request, service_slug=None):
    service = None
    if service_slug:
        service = get_object_or_404(Service, slug=service_slug, is_active=True)

    initial = {"contact_via_whatsapp": True}
    if service:
        initial["service"] = service
    if request.GET.get("service"):
        try:
            initial["service"] = Service.objects.get(slug=request.GET["service"], is_active=True)
        except Service.DoesNotExist:
            pass

    if request.method == "POST":
        if too_many_requests(request, "quote"):
            messages.error(request, "Too many requests from this connection — try again in an hour.")
            return redirect("request_quote")
        form = QuoteRequestForm(request.POST, request.FILES)
        if form.is_valid():
            quote = form.save(commit=False)
            quote.status = QuoteRequest.Status.NEW
            quote.save()
            notify_new_quote(quote)
            mail_admins(
                subject=f"[Myrai Labs] New quote request {quote.ref}",
                message=(
                    f"Ref: {quote.ref}\nService: {quote.service.name}\n"
                    f"Client: {quote.name} <{quote.email}> {quote.phone}\n"
                    f"Deadline: {quote.display_deadline}\nBudget: {quote.budget or 'n/a'}\n\n"
                    f"{quote.brief}"
                ),
                fail_silently=True,
            )
            return redirect("quote_submitted", ref=quote.ref)
        messages.error(request, "Please check the highlighted fields.")
    else:
        form = QuoteRequestForm(initial=initial)

    return render(request, "myrai/request_quote.html", {
        "form": form,
        "selected_service": service,
    })


def quote_submitted(request, ref):
    quote = get_object_or_404(QuoteRequest, ref=ref)
    return render(request, "myrai/quote_submitted.html", {"quote": quote})


def quote_status(request):
    quote = None
    looked_up = False
    pipeline_stages = [
        (QuoteRequest.Status.NEW, "New"),
        (QuoteRequest.Status.CONTACTED, "Contacted"),
        (QuoteRequest.Status.QUOTED, "Quoted"),
        (QuoteRequest.Status.IN_PROGRESS, "In progress"),
        (QuoteRequest.Status.DELIVERED, "Delivered"),
        (QuoteRequest.Status.PAID, "Paid"),
    ]
    if request.method == "POST":
        looked_up = True
        form = QuoteStatusLookupForm(request.POST)
        if form.is_valid():
            try:
                quote = QuoteRequest.objects.get(
                    ref=form.cleaned_data["ref"].strip().upper(),
                    email__iexact=form.cleaned_data["email"],
                )
            except QuoteRequest.DoesNotExist:
                quote = None
        if quote is None and looked_up:
            messages.error(request, "No order found for that reference + email combination.")
    else:
        form = QuoteStatusLookupForm()
    return render(request, "myrai/quote_status.html", {
        "form": form, "quote": quote, "pipeline_stages": pipeline_stages,
    })


# THE CONTACT
def contact(request):
    if request.method == "POST":
        if too_many_requests(request, "contact"):
            messages.error(request, "Too many messages from this connection — try again in an hour.")
            return redirect("contact")
        form = ContactForm(request.POST)
        if form.is_valid():
            msg = form.save()
            notify_contact_message(msg)
            mail_admins(
                subject=f"[Myrai Labs] Website message from {msg.name}",
                message=f"{msg.email} wrote:\n\n{msg.message}",
                fail_silently=True,
            )
            messages.success(request, "Message sent! We usually reply within a day.")
            return redirect("contact")
        messages.error(request, "Please check the highlighted fields.")
    else:
        form = ContactForm()
    return render(request, "myrai/contact.html", {
        "form": form,
        "wa_link": wa_me_link("Hi Myrai Labs! I have a question."),
    })

@csrf_exempt
@require_http_methods(["GET", "POST"])
def whatsapp_webhook(request):
    """
    GET  -> Meta's verification handshake
    POST -> incoming messages / status updates
    """
    # --- 1. Verification handshake ---
    if request.method == "GET":
        mode = request.GET.get("hub.mode")
        token = request.GET.get("hub.verify_token")
        challenge = request.GET.get("hub.challenge")

        if mode == "subscribe" and token == settings.WHATSAPP_VERIFY_TOKEN:
            logger.info("WhatsApp webhook verified.")
            return HttpResponse(challenge, status=200)

        logger.warning("WhatsApp webhook verification failed. token=%r", token)
        return HttpResponse("Forbidden", status=403)

    # --- 2. Incoming payloads ---
    try:
        payload = json.loads(request.body.decode("utf-8"))
    except (ValueError, UnicodeDecodeError):
        logger.warning("WhatsApp webhook: bad JSON")
        return HttpResponse(status=400)

    try:
        for entry in payload.get("entry", []):
            for change in entry.get("changes", []):
                value = change.get("value", {})

                # Incoming messages
                for msg in value.get("messages", []):
                    _handle_incoming_message(msg, value)

                # Delivery / read receipts
                for status in value.get("statuses", []):
                    _handle_status_update(status)

    except Exception:
        logger.exception("WhatsApp webhook processing error")

    # Always 200 so Meta doesn't retry forever
    return HttpResponse(status=200)


def _handle_incoming_message(msg, value):
    """Log incoming messages. Extend this to auto-reply, create tickets, etc."""
    from_number = msg.get("from")
    msg_type = msg.get("type")
    text = ""
    if msg_type == "text":
        text = msg.get("text", {}).get("body", "")
    logger.info("WA inbound from %s (%s): %s", from_number, msg_type, text[:200])
    # TODO: save to a model, trigger auto-reply, notify admin, etc.


def _handle_status_update(status):
    """Update WhatsAppOutbox rows with sent/delivered/read/failed."""
    from .models import WhatsAppOutbox

    msg_id = status.get("id")
    new_status = status.get("status")  # sent | delivered | read | failed
    logger.info("WA status update: %s -> %s", msg_id, new_status)
    # Optional: WhatsAppOutbox.objects.filter(provider_message_id=msg_id).update
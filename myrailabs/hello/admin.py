"""
Myrai Labs - Admin Panel
"""
from django.contrib import admin
from django.utils.html import format_html

from .models import ContactMessage, QuoteRequest, Service, ServiceCategory, WhatsAppOutbox
from .whatsapp import send_whatsapp


@admin.register(ServiceCategory)
class ServiceCategoryAdmin(admin.ModelAdmin):
    list_display = ("name", "accent", "service_count", "sort_order", "is_active")
    list_editable = ("sort_order", "is_active")
    prepopulated_fields = {"slug": ("name",)}
    search_fields = ("name",)

    @admin.display(description="Services")
    def service_count(self, obj):
        return obj.services.count()


@admin.register(Service)
class ServiceAdmin(admin.ModelAdmin):
    list_display = ("name", "category", "price_display", "featured", "is_active", "sort_order")
    list_filter = ("category", "featured", "is_active", "unit")
    list_editable = ("featured", "is_active", "sort_order")
    search_fields = ("name", "description")
    prepopulated_fields = {"slug": ("name",)}
    list_per_page = 30


class QuoteStatusFilter(admin.SimpleListFilter):
    title = "pipeline stage"
    parameter_name = "pipeline"

    def lookups(self, request, model_admin):
        return [
            ("open", "Open (new → delivered)"),
            ("done", "Closed (paid / cancelled)"),
        ]

    def queryset(self, request, queryset):
        if self.value() == "open":
            return queryset.exclude(status__in=[QuoteRequest.Status.PAID, QuoteRequest.Status.CANCELLED])
        if self.value() == "done":
            return queryset.filter(status__in=[QuoteRequest.Status.PAID, QuoteRequest.Status.CANCELLED])


@admin.register(QuoteRequest)
class QuoteRequestAdmin(admin.ModelAdmin):
    list_display = (
        "ref", "service", "name", "status_badge", "display_deadline",
        "budget", "contact_via_whatsapp", "created_at",
    )
    list_filter = ("status", "contact_via_whatsapp", "service__category", QuoteStatusFilter)
    search_fields = ("ref", "name", "email", "phone", "brief")
    readonly_fields = ("ref", "created_at", "updated_at")
    list_per_page = 30
    actions = ["mark_contacted", "mark_quoted", "mark_in_progress", "mark_delivered", "mark_paid", "push_status_whatsapp"]
    fieldsets = (
        ("Request", {"fields": ("ref", "service", "status", "created_at", "updated_at")}),
        ("Client", {"fields": ("name", "email", "phone", "contact_via_whatsapp")}),
        ("Job", {"fields": ("deadline", "budget", "brief", "attachment")}),
        ("Internal", {"fields": ("internal_notes", "whatsapp_alerted")}),
    )

    @admin.display(description="Status", ordering="status")
    def status_badge(self, obj):
        colours = {
            "NEW": "#f87171", "CONTACTED": "#fbbf24", "QUOTED": "#a78bfa",
            "IN_PROGRESS": "#22d3ee", "DELIVERED": "#34d399", "PAID": "#4ade80",
            "CANCELLED": "#94a3b8",
        }
        return format_html(
            '<b style="color:{}">{}</b>', colours.get(obj.status, "#fff"),
            obj.get_status_display(),
        )

    @admin.action(description="Mark selected as Contacted")
    def mark_contacted(self, request, queryset):
        self._transition(queryset, QuoteRequest.Status.CONTACTED)

    @admin.action(description="Mark selected as Quoted")
    def mark_quoted(self, request, queryset):
        self._transition(queryset, QuoteRequest.Status.QUOTED)

    @admin.action(description="Mark selected as In progress")
    def mark_in_progress(self, request, queryset):
        self._transition(queryset, QuoteRequest.Status.IN_PROGRESS)

    @admin.action(description="Mark selected as Delivered")
    def mark_delivered(self, request, queryset):
        self._transition(queryset, QuoteRequest.Status.DELIVERED)

    @admin.action(description="Mark selected as Paid")
    def mark_paid(self, request, queryset):
        self._transition(queryset, QuoteRequest.Status.PAID)

    def _transition(self, queryset, status):
        for quote in queryset.exclude(status=status):
            quote.status = status
            quote.save(update_fields=["status", "updated_at"])
            if status == QuoteRequest.Status.DELIVERED:
                from .whatsapp import notify_status_change
                notify_status_change(quote)

    @admin.action(description="Push status update via WhatsApp to client (opted-in only)")
    def push_status_whatsapp(self, request, queryset):
        from .whatsapp import notify_status_change
        count = 0
        for quote in queryset:
            if notify_status_change(quote):
                count += 1
        self.message_user(request, f"Queued {count} WhatsApp status updates.")


@admin.register(ContactMessage)
class ContactMessageAdmin(admin.ModelAdmin):
    list_display = ("name", "email", "short_message", "handled", "created_at")
    list_filter = ("handled",)
    list_editable = ("handled",)
    search_fields = ("name", "email", "message")
    actions = ["mark_handled", "reply_whatsapp"]

    @admin.display(description="Message")
    def short_message(self, obj):
        return (obj.message[:80] + "…") if len(obj.message) > 80 else obj.message

    @admin.action(description="Mark as handled")
    def mark_handled(self, request, queryset):
        queryset.update(handled=True)

    @admin.action(description="Ping client on WhatsApp (needs their number in message)")
    def reply_whatsapp(self, request, queryset):
        self.message_user(
            request,
            "Tip: reply directly via the click-to-chat link on the contact's email thread.",
        )


@admin.register(WhatsAppOutbox)
class WhatsAppOutboxAdmin(admin.ModelAdmin):
    list_display = ("to", "status_badge", "related_ref", "short_body", "created_at")
    list_filter = ("status",)
    search_fields = ("to", "body", "related_ref")
    readonly_fields = ("to", "body", "status", "provider_response", "related_ref", "created_at")
    actions = ["resend"]

    @admin.display(description="Status")
    def status_badge(self, obj):
        colours = {"SENT": "#34d399", "PENDING": "#fbbf24", "FAILED": "#f87171"}
        return format_html('<b style="color:{}">{}</b>', colours.get(obj.status, "#fff"), obj.status)

    @admin.display(description="Body")
    def short_body(self, obj):
        return (obj.body[:70] + "…") if len(obj.body) > 70 else obj.body

    @admin.action(description="Resend selected messages")
    def resend(self, request, queryset):
        sent = 0
        for row in queryset.exclude(status="SENT"):
            result = send_whatsapp(row.body, to=row.to, related_ref=row.related_ref)
            if result:
                sent += 1
        self.message_user(request, f"Re-queued {sent} WhatsApp messages.")


admin.site.site_header = "Myrai Labs Ops"
admin.site.site_title = "Myrai Labs"
admin.site.index_title = "Operations dashboard"
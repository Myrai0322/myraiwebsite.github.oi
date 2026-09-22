"""
Myrai Labs - The models

The models tables of the Service category, the services provided
quote requests, and also messaging.
"""

from django.db import models

# THE TIME STAMPED
class TimeStampedModel(models.Model):
    """The time handling model"""
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


# THE SERVICE CATEGORY
class ServiceCategory(models.Model):
    """The digital categories with their respective colors"""

    class Accent(models.TextChoices):
        CYAN = "cyan", "Cyan (Academic)"
        GREEN = "green", "Green (Career)"
        PURPLE = "purple", "Purple (Business)"
        ORANGE = "orange", "Orange (Technology)"

    name = models.CharField(max_length=100, unique=True)
    slug = models.SlugField(max_length=120, unique=True)
    icon = models.CharField(max_length=16, blank=True)
    accent = models.CharField(max_length=10, choices=Accent.choices, default=Accent.CYAN)
    blurb = models.CharField(max_length=250, blank=True)
    sort_order = models.PositiveIntegerField(default=0)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Service Category"
        verbose_name_plural = "Service Categories"
        ordering = ["sort_order", "name"]

    def __str__(self):
        return self.name


# THE SERVICE
class Service(models.Model):
    """A service detail model
    
    price should be nullable so that it accomodates the range design
    you feel me
    """

    class Unit(models.TextChoices):
        FIXED = "", "fixed price"
        PER_PAGE = "per_page", "Per Page"
        PER_MONTH = "per_month", "Per Month"

    category = models.ForeignKey(
        ServiceCategory, on_delete=models.CASCADE,
        related_name='services',
    )
    name = models.CharField(max_length=170, unique=True)
    slug = models.SlugField(max_length=170, unique=True)
    description = models.TextField()
    price_min = models.DecimalField(max_digits=10, decimal_places=2)
    price_max = models.DecimalField(max_digits=10, decimal_places=2, null=True,blank=True)
    open_ended = models.BooleanField(default=False)
    unit = models.CharField(max_length=12, choices=Unit.choices, default=Unit.FIXED)
    featured = models.BooleanField(default=False)
    is_active = models.BooleanField(default=True)
    sort_order = models.PositiveIntegerField(default=0)

    class Meta:
        ordering = ['sort_order', 'name']
        unique_together = [('category', 'name')]

    def __str__(self):
        return self.name

    @property
    def price_display(self):
        """Render the range style design"""
        fmt = lambda v: "R{:,.0f}".format(v)
        lo = fmt(self.price_min)
        suffix = '/pg' if self.unit == self.Unit.PER_PAGE else '/mo' if self.unit == self.Unit.PER_MONTH else '' 
        if self.price_max is not None:
            plus = '+' if self.open_ended else ''
            return f"{lo} - {fmt(self.price_max)}{suffix}{plus}"
        return f"{lo}+{suffix}" if self.open_ended else lo


# THE QUOTE REQUESTS
class QuoteRequest(TimeStampedModel):
    """Client order pipeline, Whatsapp and emaill alerts"""

    class Status(models.TextChoices):
        NEW = 'new', 'New'
        CONTACTED = 'contacted', 'Contacted'
        QUOTED = 'quoted', 'Quoted'
        IN_PROGRESS = 'in_progress', 'In Progress'
        DELIVERED = 'delivered', 'Delivered'
        PAID = 'paid', 'Paid'
        CANCELLED = 'cancelled', 'Cancelled'

    ref = models.CharField(max_length=20, unique=True, db_index=True)
    service = models.ForeignKey(
        Service, on_delete=models.PROTECT,
        related_name='quote_requests',
    )
    name = models.CharField(max_length=120)
    email = models.EmailField()
    phone = models.CharField(max_length=20, blank=True)
    contact_via_whatsapp = models.BooleanField(default=False)
    deadline = models.DateField(null=True, blank=True)
    budget = models.DecimalField(max_digits=10, decimal_places=2, null=True, blank=True)
    brief = models.TextField(max_length=4000)
    attachment = models.FileField(
        upload_to="quote_briefs/%y/%m", blank=True, max_length=255,
    )
    status = models.CharField(max_length=20, choices=Status.choices, default=Status.NEW)
    internal_notes = models.TextField(blank=True)
    whatsapp_alerted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.ref} · {self.service.name} · {self.get_status_display()}"

    def save(self, *args, **kwargs):
        if not self.ref:
            self.ref = self.generate_ref()
        super().save(*args, **kwargs)

    @staticmethod
    def generate_ref():
        import secrets
        from django.utils import timezone

        year = timezone.now().year
        while True:
            ref = f"ML-{year}-{secrets.randbelow(9000) + 1000}"
            if not QuoteRequest.objects.filter(ref=ref).exists():
                return ref

    @property
    def display_deadline(self):
        return self.deadline.strftime("%d %b %y") if self.deadline else "Flexible"

    PIPELINE = [Status.NEW, Status.CONTACTED, Status.QUOTED, Status.IN_PROGRESS, Status.DELIVERED, Status.PAID]

    @property
    def past_stages(self):
        """Statges at or before the current one"""
        if self.status == self.Status.CANCELLED:
            return []
        try:
            idx = self.PIPELINE.index(self.Status(self.status))
        except ValueError:
            return []
        return [stage for stage in self.PIPELINE[: idx + 1]]


# THE CONTACT MESSAGING
class ContactMessage(TimeStampedModel):
    name = models.CharField(max_length=120)
    email = models.EmailField()
    message = models.TextField(max_length=3000)
    handled = models.BooleanField(default=False)
    whatsapp_alerted = models.BooleanField(default=False)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f"{self.name} <{self.email}>"


# THE WHATSAPP OUTBOX
class WhatsAppOutbox(TimeStampedModel):
    """Audit log + retry queue for every outbound WhatsApp alert."""

    class Status(models.TextChoices):
        PENDING = "PENDING", "Pending"
        SENT = "SENT", "Sent"
        FAILED = "FAILED", "Failed"

    to = models.CharField(max_length=20)
    body = models.TextField()
    status = models.CharField(max_length=8, choices=Status.choices, default=Status.PENDING)
    provider_response = models.TextField(blank=True)
    related_ref = models.CharField(max_length=20, blank=True)

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "WhatsApp outbox entry"
        verbose_name_plural = "WhatsApp outbox"

    def __str__(self):
        return f"{self.to} · {self.status}"
"""Myrai Labs test suite.

Run:  python manage.py test hello
"""
from datetime import date, timedelta

from django.core import mail
from django.core.cache import cache
from django.test import Client, TestCase, override_settings
from django.urls import reverse

from .models import ContactMessage, QuoteRequest, Service, ServiceCategory, WhatsAppOutbox
from .whatsapp import normalise_sa_number, wa_me_link

POSTER_PRICES = {
    # name: (min, max or None, open_ended, unit)
    "Assignments Writing": (150, 500, False, ""),
    "Research Assignments": (300, 1000, True, ""),
    "Editing & Proofreading": (50, 150, False, "per page"),
    "Paraphrasing": (80, 200, False, "per page"),
    "Typing": (20, 50, False, "per page"),
    "PowerPoint Presentations": (150, 400, False, ""),
    "Posters": (100, 300, False, ""),
    "ETP / ECL Portfolios": (300, 800, False, ""),
    "Excel & Publisher Tasks": (100, 400, False, ""),
    "CV Writing": (300, 1000, False, ""),
    "Cover Letters": (100, 250, False, ""),
    "Full Package (CV + Cover)": (400, 1200, False, ""),
    "Professional Portfolios": (300, 800, False, ""),
    "Business Plans": (1000, 5000, False, ""),
    "Business Profiles": (500, 2000, False, ""),
    "Research Projects": (800, 3000, True, ""),
    "Company Registration": (500, 1500, False, ""),
    "Basic Websites": (2000, 8000, False, ""),
    "Standard Websites": (8000, 20000, False, ""),
    "Portfolio Websites": (1000, 5000, False, ""),
    "Web Apps (Django/Python)": (15000, 50000, True, ""),
    "Maintenance": (200, 500, False, "per month"),
}


class PosterCatalogueTests(TestCase):
    """The poster is the single source of truth for every price on the site."""

    def test_all_22_poster_services_exist(self):
        for name in POSTER_PRICES:
            self.assertTrue(
                Service.objects.filter(name=name).exists(),
                f"Missing poster service: {name}",
            )
        self.assertEqual(Service.objects.count(), 22)
        self.assertEqual(ServiceCategory.objects.count(), 4)

    def test_prices_match_poster_exactly(self):
        for name, (pmin, pmax, open_ended, unit) in POSTER_PRICES.items():
            svc = Service.objects.get(name=name)
            self.assertEqual(float(svc.price_min), pmin, f"{name} min price wrong")
            if pmax is None:
                self.assertIsNone(svc.price_max, f"{name} should have no max")
            else:
                self.assertEqual(float(svc.price_max), pmax, f"{name} max price wrong")
            self.assertEqual(svc.open_ended, open_ended, f"{name} open_ended wrong")
            self.assertEqual(svc.unit, unit, f"{name} unit wrong")

    def test_price_display_matches_poster_format(self):
        self.assertEqual(Service.objects.get(name="Assignments Writing").price_display, "R150 – R500")
        self.assertEqual(Service.objects.get(name="Research Assignments").price_display, "R300 – R1,000+")
        self.assertEqual(Service.objects.get(name="Editing & Proofreading").price_display, "R50 – R150/pg")
        self.assertEqual(Service.objects.get(name="Maintenance").price_display, "R200 – R500/mo")
        self.assertEqual(Service.objects.get(name="Basic Websites").price_display, "R2,000 – R8,000")
        self.assertEqual(Service.objects.get(name="Web Apps (Django/Python)").price_display, "R15,000 – R50,000+")


class AuthTests(TestCase):
    """The original login view read username as password and always 'succeeded'."""

    def setUp(self):
        from .forms import CustomUserForm

        self.client = Client()
        form = CustomUserForm(data={
            "username": "thabo",
            "email": "thabo@example.com",
            "password1": "str0ng-Passw0rd!",
            "password2": "str0ng-Passw0rd!",
        })
        self.assertTrue(form.is_valid(), form.errors)
        form.save()
        cache.clear()

    def test_login_with_correct_password(self):
        resp = self.client.post(reverse("login"), {"username": "thabo", "password": "str0ng-Passw0rd!"})
        self.assertRedirects(resp, reverse("index"))
        self.assertTrue("_auth_user_id" in self.client.session)

    def test_login_with_wrong_password_is_rejected(self):
        resp = self.client.post(reverse("login"), {"username": "thabo", "password": "wrong-pass"})
        self.assertEqual(resp.status_code, 200)
        self.assertFalse("_auth_user_id" in self.client.session)
        self.assertContains(resp, "Wrong username or password")

    def test_register_then_auto_login(self):
        resp = self.client.post(reverse("register"), {
            "username": "lerato",
            "email": "lerato@example.com",
            "password1": "anoth3r-Pass!",
            "password2": "anoth3r-Pass!",
        })
        self.assertRedirects(resp, reverse("index"))
        self.assertTrue("_auth_user_id" in self.client.session)

    def test_logout(self):
        self.client.post(reverse("login"), {"username": "thabo", "password": "str0ng-Passw0rd!"})
        resp = self.client.post(reverse("logout"))
        self.assertRedirects(resp, reverse("index"))
        self.assertFalse("_auth_user_id" in self.client.session)


class PageTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_root_is_homepage_not_register(self):
        resp = self.client.get("/")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "MYRAI")

    def test_public_pages_render(self):
        for url in ["/services/", "/about/", "/contact/", "/quote/", "/quote/status/",
                    "/auth/login/", "/auth/register/"]:
            resp = self.client.get(url)
            self.assertEqual(resp.status_code, 200, f"{url} failed")

    def test_services_page_shows_poster_prices(self):
        resp = self.client.get("/services/")
        self.assertContains(resp, "R2,000 – R8,000")      # Basic Websites (poster, not old R5,000–R15,000)
        self.assertContains(resp, "R150 – R500")          # Assignments Writing
        self.assertContains(resp, "R15,000 – R50,000+")   # Web Apps
        self.assertNotContains(resp, "R5,000 - R15,000")  # old draft price must be gone


class QuoteFlowTests(TestCase):
    def setUp(self):
        cache.clear()
        self.svc = Service.objects.get(name="CV Writing")

    def _valid_data(self, **overrides):
        data = {
            "service": self.svc.pk,
            "name": "Naledi M",
            "email": "naledi@example.com",
            "phone": "071 234 5678",
            "contact_via_whatsapp": "on",
            "deadline": (date.today() + timedelta(days=7)).isoformat(),
            "budget": "600",
            "brief": "Need a CV for a graduate programme application.",
            "website": "",
        }
        data.update(overrides)
        return data

    def test_quote_submission_full_pipeline(self):
        resp = self.client.post("/quote/", self._valid_data())
        self.assertEqual(resp.status_code, 302)
        quote = QuoteRequest.objects.get(email="naledi@example.com")
        self.assertTrue(quote.ref.startswith("ML-"))
        self.assertEqual(quote.status, QuoteRequest.Status.NEW)
        # owner got a WhatsApp outbox entry + admin got an email
        self.assertEqual(WhatsAppOutbox.objects.filter(related_ref=quote.ref).count(), 1)
        self.assertEqual(len(mail.outbox), 1)
        # thank-you page shows the ref
        resp = self.client.get(f"/quote/thanks/{quote.ref}/")
        self.assertContains(resp, quote.ref)

    def test_honeypot_rejects_bots(self):
        resp = self.client.post("/quote/", self._valid_data(website="http://spam.example"))
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(QuoteRequest.objects.count(), 0)

    def test_status_lookup_with_ref_and_email(self):
        self.client.post("/quote/", self._valid_data())
        quote = QuoteRequest.objects.get(email="naledi@example.com")
        resp = self.client.post("/quote/status/", {"ref": quote.ref, "email": "naledi@example.com"})
        self.assertContains(resp, quote.ref)
        self.assertContains(resp, "New")

    def test_status_lookup_requires_matching_email(self):
        self.client.post("/quote/", self._valid_data())
        quote = QuoteRequest.objects.get(email="naledi@example.com")
        resp = self.client.post("/quote/status/", {"ref": quote.ref, "email": "wrong@example.com"})
        self.assertNotContains(resp, "status-card")

    def test_rate_limit_blocks_flood(self):
        for _ in range(5):
            self.client.post("/quote/", self._valid_data(email=f"u{QuoteRequest.objects.count()}@example.com"))
        resp = self.client.post("/quote/", self._valid_data(email="flood@example.com"), follow=True)
        self.assertEqual(QuoteRequest.objects.filter(email="flood@example.com").count(), 0)


class ContactTests(TestCase):
    def setUp(self):
        cache.clear()

    def test_contact_form_saves_and_alerts(self):
        resp = self.client.post("/contact/", {
            "name": "Sipho", "email": "sipho@example.com",
            "message": "Do you do company registrations in Giyani?", "website": "",
        })
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(ContactMessage.objects.count(), 1)
        self.assertEqual(WhatsAppOutbox.objects.count(), 1)
        self.assertEqual(len(mail.outbox), 1)

    def test_honeypot_blocks_contact_spam(self):
        self.client.post("/contact/", {
            "name": "Bot", "email": "bot@bot.bot", "message": "buy now", "website": "x",
        })
        self.assertEqual(ContactMessage.objects.count(), 0)


class WhatsAppHelperTests(TestCase):
    def test_normalise_sa_number(self):
        self.assertEqual(normalise_sa_number("078 233 9131"), "27782339131")
        self.assertEqual(normalise_sa_number("+27 78 233 9131"), "27782339131")
        self.assertEqual(normalise_sa_number("27782339131"), "27782339131")

    def test_wa_me_link_from_poster_number(self):
        link = wa_me_link("Hi!")
        self.assertTrue(link.startswith("https://wa.me/27782339131?text="), link)

    def test_failed_send_never_raises(self):
        # No credentials configured -> must queue as PENDING, not crash
        row = WhatsAppOutbox.objects.create(to="27782339131", body="ping")
        from .whatsapp import _deliver
        _deliver(row.pk, "27782339131", "ping", "")
        row.refresh_from_db()
        self.assertEqual(row.status, WhatsAppOutbox.Status.PENDING)
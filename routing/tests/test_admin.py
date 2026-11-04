import os
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import TestCase
from django.urls import reverse

from routing.models import FuelStation


def create_station(opis_id: int, city: str, state: str, price: str) -> FuelStation:
    return FuelStation.objects.create(
        opis_id=opis_id,
        name=f"STOP #{opis_id}",
        address="I-35",
        city=city,
        state=state,
        rack_id=1,
        retail_price=Decimal(price),
        latitude=32.8,
        longitude=-96.8,
    )


class FuelStationAdminTests(TestCase):
    url = reverse("admin:routing_fuelstation_changelist")

    def setUp(self):
        self.client.force_login(
            get_user_model().objects.create_superuser("admin", "admin@example.com", "pw")
        )
        create_station(1, "Dallas", "TX", "2.864")
        create_station(2, "Denver", "CO", "3.149")

    def test_lists_stations(self):
        response = self.client.get(self.url)

        self.assertContains(response, "STOP #1")
        self.assertContains(response, "Dallas, TX")
        self.assertContains(response, "$2.864")

    def test_filters_by_state(self):
        response = self.client.get(self.url, {"state": "CO"})

        self.assertContains(response, "STOP #2")
        self.assertNotContains(response, "STOP #1")

    def test_filters_by_price_range(self):
        response = self.client.get(self.url, {"retail_price_from": "3", "retail_price_to": "4"})

        self.assertContains(response, "STOP #2")
        self.assertNotContains(response, "STOP #1")

    def test_searches_by_city(self):
        response = self.client.get(self.url, {"q": "Denver"})

        self.assertContains(response, "STOP #2")
        self.assertNotContains(response, "STOP #1")

    def test_stations_are_read_only(self):
        station = FuelStation.objects.get(opis_id=1)

        with self.assertLogs("django.request", "WARNING"):  # Django logs the 403.
            add = self.client.get(reverse("admin:routing_fuelstation_add"))
        self.assertEqual(add.status_code, 403)
        detail = self.client.get(reverse("admin:routing_fuelstation_change", args=[station.pk]))
        self.assertEqual(detail.status_code, 200)  # Viewable...
        self.assertNotContains(detail, 'name="_save"')  # ...but not editable.

    def test_dashboard_uses_unfold(self):
        response = self.client.get(reverse("admin:index"))

        self.assertContains(response, "Fuel Route Optimizer")
        self.assertContains(response, "unfold")


class AdminLoginPageTests(TestCase):
    def test_shows_the_truck_illustration(self):
        response = self.client.get(reverse("admin:login"))

        self.assertContains(response, "routing/admin-login.svg")


class EnsureSuperuserTests(TestCase):
    def run_command(self, **env) -> str:
        out = StringIO()
        with mock.patch.dict(os.environ, env, clear=False):
            for name in ("DJANGO_SUPERUSER_USERNAME", "DJANGO_SUPERUSER_PASSWORD"):
                if name not in env:
                    os.environ.pop(name, None)
            call_command("ensure_superuser", stdout=out)
        return out.getvalue()

    def test_creates_admin_from_environment(self):
        output = self.run_command(DJANGO_SUPERUSER_USERNAME="boss", DJANGO_SUPERUSER_PASSWORD="pw")

        user = get_user_model().objects.get(username="boss")
        self.assertTrue(user.is_superuser)
        self.assertTrue(user.check_password("pw"))
        self.assertIn("Created admin user 'boss'", output)

    def test_is_idempotent(self):
        env = {"DJANGO_SUPERUSER_USERNAME": "boss", "DJANGO_SUPERUSER_PASSWORD": "pw"}
        self.run_command(**env)

        output = self.run_command(**env)

        self.assertEqual(get_user_model().objects.filter(username="boss").count(), 1)
        self.assertIn("already exists", output)

    def test_does_nothing_without_credentials(self):
        output = self.run_command()

        self.assertFalse(get_user_model().objects.exists())
        self.assertIn("not set", output)

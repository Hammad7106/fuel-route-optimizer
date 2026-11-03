from django.core.management import call_command
from django.test import SimpleTestCase, TestCase
from django.urls import reverse


class OpenApiSchemaTests(SimpleTestCase):
    def test_schema_is_valid_and_has_no_warnings(self):
        # --fail-on-warn turns any schema generation warning into an error.
        call_command("spectacular", "--validate", "--fail-on-warn", stdout=open("/dev/null", "w"))


class DocsViewTests(TestCase):
    def test_swagger_ui_is_served(self):
        response = self.client.get(reverse("swagger-ui"))

        self.assertContains(response, "swagger-ui")

    def test_schema_documents_the_trip_endpoint(self):
        response = self.client.get(reverse("schema"), {"format": "json"})

        operation = response.json()["paths"]["/api/route/"]["post"]
        self.assertEqual(set(operation["responses"]), {"200", "400", "422", "503"})

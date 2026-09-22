"""Verifies the generated OpenAPI contract matches actual app behavior:
validation failures are documented as 400 (not FastAPI's default 422), and
success/error response shapes are explicit.
"""

# `tests.base` must be imported before anything under `app.*` - see the
# note in tests/test_api.py and tests/__init__.py.
from tests.base import ApiTestCase

from app.models import COMMENT_MAX_LENGTH, CONTACT_MAX_LENGTH, NAME_MAX_LENGTH, SOURCE_MAX_LENGTH


class OpenApiContractTests(ApiTestCase):
    @classmethod
    def setUpClass(cls) -> None:
        super().setUpClass()
        response = cls.client.get("/openapi.json")
        assert response.status_code == 200
        cls.schema = response.json()

    def _resolve(self, ref: str) -> dict:
        # "#/components/schemas/LeadResponse" -> schema dict
        name = ref.rsplit("/", 1)[-1]
        return self.schema["components"]["schemas"][name]

    def test_health_success_response_is_explicit(self) -> None:
        responses = self.schema["paths"]["/health"]["get"]["responses"]
        self.assertIn("200", responses)
        schema_ref = responses["200"]["content"]["application/json"]["schema"]["$ref"]
        health_schema = self._resolve(schema_ref)
        self.assertIn("status", health_schema["properties"])

    def test_lead_success_response_is_explicit(self) -> None:
        responses = self.schema["paths"]["/lead"]["post"]["responses"]
        self.assertIn("200", responses)
        schema_ref = responses["200"]["content"]["application/json"]["schema"]["$ref"]
        lead_schema = self._resolve(schema_ref)
        self.assertEqual(set(lead_schema["properties"]), {"id", "message"})

    def test_lead_documents_400_for_validation_failures(self) -> None:
        responses = self.schema["paths"]["/lead"]["post"]["responses"]
        self.assertIn("400", responses)
        schema_ref = responses["400"]["content"]["application/json"]["schema"]["$ref"]
        error_schema = self._resolve(schema_ref)
        self.assertIn("detail", error_schema["properties"])

    def test_lead_documents_generic_500(self) -> None:
        responses = self.schema["paths"]["/lead"]["post"]["responses"]
        self.assertIn("500", responses)
        schema_ref = responses["500"]["content"]["application/json"]["schema"]["$ref"]
        error_schema = self._resolve(schema_ref)
        self.assertIn("detail", error_schema["properties"])

    def test_lead_does_not_advertise_stale_422(self) -> None:
        """The app converts validation errors to 400 itself; it never
        returns FastAPI's default 422, so OpenAPI must not claim it does."""
        responses = self.schema["paths"]["/lead"]["post"]["responses"]
        self.assertNotIn("422", responses)

    def test_lead_create_schema_documents_field_length_limits(self) -> None:
        lead_create = self.schema["components"]["schemas"]["LeadCreate"]
        properties = lead_create["properties"]
        self.assertEqual(properties["contact"]["maxLength"], CONTACT_MAX_LENGTH)
        self.assertEqual(properties["name"]["anyOf"][0]["maxLength"], NAME_MAX_LENGTH)
        self.assertEqual(properties["source"]["anyOf"][0]["maxLength"], SOURCE_MAX_LENGTH)
        self.assertEqual(properties["comment"]["anyOf"][0]["maxLength"], COMMENT_MAX_LENGTH)

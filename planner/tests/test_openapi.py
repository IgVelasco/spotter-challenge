from io import StringIO

import yaml
from django.core.management import call_command


def generated_schema(tmp_path):
    path = tmp_path / "schema.yaml"
    call_command(
        "spectacular", "--validate", "--fail-on-warn", "--file", str(path), stderr=StringIO()
    )
    return yaml.safe_load(path.read_text())


def test_schema_is_valid_openapi_without_warnings(tmp_path):
    schema = generated_schema(tmp_path)

    assert schema["openapi"].startswith("3.")
    assert "/api/v1/route-plan/" in schema["paths"]


def test_route_plan_documents_its_inputs_examples_and_errors(tmp_path):
    operation = generated_schema(tmp_path)["paths"]["/api/v1/route-plan/"]["post"]

    request = operation["requestBody"]["content"]["application/json"]
    assert request["examples"]
    responses = operation["responses"]
    assert {"200", "400", "422", "429", "502"} <= set(responses)
    assert responses["200"]["content"]["application/json"]["examples"]
    assert responses["422"]["content"]["application/json"]["examples"]


def test_location_fields_accept_text_or_coordinates(tmp_path):
    schema = generated_schema(tmp_path)
    fields = schema["components"]["schemas"]["TripRequest"]["properties"]

    variants = fields["start"]["oneOf"]
    assert {"type": "string", "maxLength": 255} in [
        {k: v for k, v in variant.items() if k in ("type", "maxLength")} for variant in variants
    ]
    assert any(variant.get("type") == "object" for variant in variants)


def test_interactive_docs_page_is_served(client):
    response = client.get("/api/v1/docs/")

    assert response.status_code == 200
    assert b"swagger-ui" in response.content


def test_schema_endpoint_is_served(client):
    response = client.get("/api/v1/schema/")

    assert response.status_code == 200
    assert b"openapi: 3" in response.content

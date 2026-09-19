from brin_hotspot.auth import application_roles


def test_application_roles_are_client_scoped():
    claims = {
        "resource_access": {
            "hotspot-new": {"roles": ["sage", "unrelated"]},
            "geocatalog": {"roles": ["god"]},
        }
    }

    assert application_roles(claims, "hotspot-new") == {"sage"}

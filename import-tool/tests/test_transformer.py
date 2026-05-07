from transformer import get_fields, ENTITY_TYPES

def test_guest_required_fields():
    fields = get_fields("guest")
    required = [f["name"] for f in fields if f["required"]]
    assert set(required) == {"first_name", "last_name", "email"}

def test_company_required_fields():
    fields = get_fields("company")
    required = [f["name"] for f in fields if f["required"]]
    assert set(required) == {"name", "email"}

def test_reservation_required_fields():
    fields = get_fields("reservation")
    required = [f["name"] for f in fields if f["required"]]
    assert set(required) == {"first_name", "last_name", "email", "Check In", "Check Out", "Zimmer", "Zimmertyp"}

def test_entity_types_known():
    assert set(ENTITY_TYPES) == {"guest", "company", "reservation"}

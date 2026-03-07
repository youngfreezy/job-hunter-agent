from backend.browser.tools.form_filler import _enforce_required_field_fallbacks


def test_required_contact_fields_use_profile_values():
    fields = [
        {
            "selector": "#email",
            "label": "Email",
            "type": "email",
            "required": True,
            "options": [],
        },
        {
            "selector": "#phone",
            "label": "Phone",
            "type": "tel",
            "required": True,
            "options": [],
        },
        {
            "selector": "#name",
            "label": "Full Name",
            "type": "text",
            "required": True,
            "options": [],
        },
    ]
    instructions = [
        {"selector": "#email", "action": "fill", "value": "", "field_name": "Email"},
        {"selector": "#phone", "action": "skip", "value": "", "field_name": "Phone"},
    ]

    result = _enforce_required_field_fallbacks(
        fields,
        instructions,
        {
            "email": "jane.doe@example.com",
            "phone": "+1 555 111 2222",
            "name": "Jane Doe",
        },
    )

    assert result[0]["value"] == "jane.doe@example.com"
    assert result[1]["value"] == "+1 555 111 2222"
    name_instruction = next(item for item in result if item["selector"] == "#name")
    assert name_instruction["value"] == "Jane Doe"

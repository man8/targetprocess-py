"""Tests for Term model."""

from targetprocess.models import Term


def test_term_full_parsing() -> None:
    term = Term.model_validate(
        {
            "Id": 11,
            "ResourceType": "Term",
            "WordKey": "UserStory",
            "Value": "Ticket",
            "Process": {"ResourceType": "Process", "Id": 2, "Name": "Scrum"},
            "EntityType": {"ResourceType": "EntityType", "Id": 4, "Name": "UserStory"},
        }
    )
    assert term.id == 11
    assert term.word_key == "UserStory"
    assert term.value == "Ticket"
    assert term.process is not None and term.process.id == 2
    assert term.entity_type is not None and term.entity_type.name == "UserStory"
    assert term.model_extra == {}


def test_term_has_no_name() -> None:
    # /meta declares no Name on a Term, so it extends Entity directly.
    term = Term.model_validate({"Id": 1, "WordKey": "Bug", "Value": "Defect"})
    assert not hasattr(term, "name")
    assert not hasattr(term, "Name")


def test_term_preserves_undeclared_fields() -> None:
    term = Term.model_validate({"Id": 1, "WordKey": "Bug", "Value": "Defect", "Plural": "Defects"})
    assert term.model_extra is not None
    assert term.model_extra["Plural"] == "Defects"

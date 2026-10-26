import pytest
from pydantic import ValidationError

from app.schemas.customer_feedback import (
    CustomerFeedbackCreate,
    CustomerFeedbackUpdate,
    ProductRoadmapItemCreate,
)


def test_customer_feedback_normalizes_text() -> None:
    payload = CustomerFeedbackCreate(
        title="  Export filtering  ",
        category="IMPROVEMENT",
        description="  Allow filtering of exported compliance reports.  ",
    )
    assert payload.title == "Export filtering"
    assert payload.description == "Allow filtering of exported compliance reports."


def test_customer_feedback_rejects_blank_descriptions() -> None:
    with pytest.raises(ValidationError):
        CustomerFeedbackCreate(
            title="Useful feature",
            category="FEATURE_REQUEST",
            description="          ",
        )


def test_feedback_update_requires_a_change_and_rejects_null_status() -> None:
    with pytest.raises(ValidationError):
        CustomerFeedbackUpdate()
    with pytest.raises(ValidationError):
        CustomerFeedbackUpdate(status=None)
    assert CustomerFeedbackUpdate(roadmap_item_id=None).model_fields_set == {
        "roadmap_item_id"
    }


def test_internal_roadmap_is_the_default_visibility() -> None:
    payload = ProductRoadmapItemCreate(title="Roadmap item")
    assert payload.visibility == "INTERNAL"
    assert payload.status == "PROPOSED"

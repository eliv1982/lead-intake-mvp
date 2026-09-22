from typing import Literal, Optional

from pydantic import BaseModel, Field, field_validator

# Modest MVP length limits. These exist only to reject meaningless oversized
# payloads (e.g. a 10,000-character "contact" value) - they are not an email
# or phone validation library and do not change the accepted contact format.
CONTACT_MAX_LENGTH = 255
NAME_MAX_LENGTH = 200
SOURCE_MAX_LENGTH = 100
COMMENT_MAX_LENGTH = 2000


class LeadCreate(BaseModel):
    name: Optional[str] = Field(default=None, max_length=NAME_MAX_LENGTH)
    contact: str = Field(max_length=CONTACT_MAX_LENGTH)
    source: Optional[str] = Field(default=None, max_length=SOURCE_MAX_LENGTH)
    comment: Optional[str] = Field(default=None, max_length=COMMENT_MAX_LENGTH)

    @field_validator("contact")
    @classmethod
    def contact_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Field 'contact' is required and must not be empty.")
        return value.strip()


class HealthResponse(BaseModel):
    """Actual shape returned by GET /health."""

    status: Literal["ok"]


class LeadResponse(BaseModel):
    """Actual shape returned by POST /lead on success."""

    id: int
    message: Literal["Lead saved successfully."]


class ErrorResponse(BaseModel):
    """Generic error shape used for both the 400 and 500 responses.

    Never contains raw exception text, SQL, or filesystem paths.
    """

    detail: str

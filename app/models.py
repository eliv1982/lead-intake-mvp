from typing import Optional

from pydantic import BaseModel, field_validator


class LeadCreate(BaseModel):
    name: Optional[str] = None
    contact: str
    source: Optional[str] = None
    comment: Optional[str] = None

    @field_validator("contact")
    @classmethod
    def contact_must_not_be_empty(cls, value: str) -> str:
        if not value or not value.strip():
            raise ValueError("Field 'contact' is required and must not be empty.")
        return value.strip()

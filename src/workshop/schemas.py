"""Small shared contract for the provisional pack and later imports."""
from decimal import Decimal
from typing import Literal
from pydantic import BaseModel, ConfigDict, Field, field_validator

class Strict(BaseModel):
    model_config = ConfigDict(extra="forbid", allow_inf_nan=False)

class PageRef(Strict):
    invoice_id: str
    page: int = Field(ge=1, le=20)
    sha256: str = Field(pattern=r"^[a-f0-9]{64}$")

class Line(Strict):
    id: str
    description: str
    quantity: Decimal = Field(gt=0, le=1000000)
    uom: str
    unit_price: Decimal = Field(ge=0, le=1000000)
    net: Decimal = Field(ge=0, le=1000000000)
    page_ref: PageRef

class Invoice(Strict):
    id: str
    supplier_id: str
    invoice_number: str
    po_id: str
    bank_account: str
    currency: Literal["EUR"]
    net: Decimal = Field(ge=0, le=1000000000)
    tax: Decimal = Field(ge=0, le=1000000000)
    gross: Decimal = Field(ge=0, le=1000000000)
    lines: list[Line] = Field(min_length=1, max_length=50)

class Extraction(Strict):
    version: str
    source: Literal["verified-fixture", "live-vlm"]
    invoice_sha256: str
    original: Invoice
    candidate: Invoice

class Evidence(Strict):
    id: str
    page_ref: PageRef
    field: str
    value: str
    confidence: Literal["clear", "ambiguous", "unavailable"]
    excerpt: str = Field(max_length=2000)
    origin: Literal["recorded-page-observation", "live-page-review"]

class PageReviewResult(Strict):
    observations: list[Evidence] = Field(max_length=20)

class Coverage(Strict):
    dataset: str
    status: Literal["complete", "selected", "unavailable"]
    description: str

class Check(Strict):
    id: str
    status: Literal["pass", "unresolved", "blocking"]
    detail: str
    evidence_ids: list[str] = []

class ToolRequest(Strict):
    name: Literal["review_pdf_page"]
    invoice_id: str
    page: int = Field(ge=1, le=20)

class Correction(Strict):
    field: str
    value: str = Field(max_length=100)
    evidence_id: str

class Finding(Strict):
    evidence_ids: list[str] = Field(default_factory=list, max_length=20)
    corrections: list[Correction] = Field(default_factory=list, max_length=10)
    note: str = Field(default="", max_length=2000)

class InvestigationResult(Strict):
    tool_requests: list[ToolRequest] = Field(default_factory=list, max_length=1)
    findings: Finding = Field(default_factory=Finding)
    handoff: str | None = Field(default=None, max_length=2000)

    @field_validator("handoff")
    @classmethod
    def nonblank(cls, value):
        if value is not None and not value.strip():
            raise ValueError("handoff must explain why")
        return value

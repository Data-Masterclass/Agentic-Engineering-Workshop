"""Small allowlisted read-only tools; only returned evidence enters validation."""
import copy
from pydantic import BaseModel, ConfigDict, Field
from .data import digest
from .store import Store
from .pdf import page_reference, validate_observations


class SupplierArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    supplier_id: str = Field(min_length=1, max_length=80)


class SearchArgs(SupplierArgs):
    requisition: str = Field(min_length=1, max_length=80)


class OrderArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    order_id: str = Field(min_length=1, max_length=80)


class HistoryArgs(SupplierArgs):
    invoice_number: str = Field(min_length=1, max_length=80)


class PageArgs(BaseModel):
    model_config = ConfigDict(extra="forbid", strict=True)
    page: int = Field(ge=1, le=1)


ARGUMENTS = {
    "get_supplier": SupplierArgs, "search_purchase_orders": SearchArgs,
    "get_purchase_order": OrderArgs, "get_receipts": OrderArgs,
    "get_invoice_history": HistoryArgs, "review_pdf_page": PageArgs,
}
DESCRIPTIONS = {
    "get_supplier": "Read the selected supplier master within this invoice's buyer scope.",
    "search_purchase_orders": "Find selected order candidates by supplier and exact requisition; retrieve a candidate before using it.",
    "get_purchase_order": "Read an in-scope order, preserving its distinct identity and printed values.",
    "get_receipts": "Read selected receipts; empty selected results never establish absence or complete coverage.",
    "get_invoice_history": "Search selected history by invoice number, ignoring only spaces, hyphens and slashes. Positive matches need corroboration.",
    "review_pdf_page": "Read the selected invoice PDF page for direct quantity corroboration. Live mode uses an image-based model read; offline mode uses a labelled recording.",
}
TOOLS = [{"type": "function", "name": name, "description": DESCRIPTIONS[name],
          "parameters": args.model_json_schema(), "strict": True} for name, args in ARGUMENTS.items()]


def normalized_number(value):
    return value.translate(str.maketrans("", "", " -/"))


class EvidenceTools:
    def __init__(self, packet):
        if digest(packet["records"]) != packet["source_hash"]:
            raise ValueError("synthetic source hash differs from fixture")
        self._packet = copy.deepcopy(packet)
        self._store = Store(packet)
        self.evidence = []
        self.seen = set()

    def close(self):
        self._store.close()

    def execute(self, name, raw, *, page_reader=None):
        if name not in ARGUMENTS:
            raise ValueError("tool is not allowed")
        args = ARGUMENTS[name].model_validate(raw).model_dump()
        key = (name, digest(args))
        if key in self.seen:
            raise ValueError("duplicate tool request makes no progress")
        self.seen.add(key)
        invoice = self._packet["invoice"]
        if "supplier_id" in args and args["supplier_id"] != invoice["supplier_id"]:
            raise ValueError("supplier outside the selected invoice scope")
        scope = {"buyer_id": invoice["buyer_id"], "supplier_id": invoice["supplier_id"]}
        orders = self._store.select("orders", **scope)
        if "order_id" in args and args["order_id"] not in {r["id"] for r in orders}:
            raise ValueError("order outside the selected invoice scope")
        if name == "get_supplier":
            rows = self._store.select("suppliers", record_id=args["supplier_id"], buyer_id=invoice["buyer_id"])
        elif name == "search_purchase_orders":
            rows = [{k: r[k] for k in ("id", "requisition", "product")} for r in self._store.select("orders", **scope, requisition=args["requisition"])]
        elif name == "get_purchase_order":
            rows = self._store.select("orders", **scope, record_id=args["order_id"])
        elif name == "get_receipts":
            rows = self._store.select("receipts", **scope, order_id=args["order_id"])
        elif name == "get_invoice_history":
            if normalized_number(args["invoice_number"]) != normalized_number(invoice["invoice_number"]):
                raise ValueError("history query differs from selected invoice")
            rows = self._store.select("history", **scope, invoice_key=normalized_number(args["invoice_number"]))
        else:
            reference = page_reference(invoice["id"])
            if reference != invoice["page_ref"]:
                raise ValueError("invoice page reference differs from verified fixture")
            if page_reader is not None:
                rows = page_reader(invoice["id"], args["page"])
            else:
                rows = [{k: v for k, v in row.items() if k != "page"} for row in self._store.select("pages", **scope, page=args["page"])]
            rows = validate_observations(rows, reference, live=page_reader is not None)
        result = {"id": f"e{len(self.evidence) + 1}", "tool": name, "arguments": args,
                  "coverage": "selected", "as_of": None, "source_hash": self._packet["source_hash"],
                  "records": copy.deepcopy(rows), "record_hash": digest(rows), "mode": "live-page-review" if name == "review_pdf_page" and page_reader is not None else "synthetic-recorded"}
        self.evidence.append(copy.deepcopy(result))
        return result

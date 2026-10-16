"""Selected synthetic case records in a small read-only SQLite source."""
import json
import sqlite3


class Store:
    def __init__(self, packet):
        # Budget runs operations in sequential worker threads. No writes follow seed.
        self._db = sqlite3.connect(":memory:", check_same_thread=False)
        self._db.execute("CREATE TABLE records (dataset TEXT, buyer_id TEXT, supplier_id TEXT, record_id TEXT, order_id TEXT, requisition TEXT, invoice_key TEXT, page INTEGER, payload TEXT)")
        invoice = packet["invoice"]
        for dataset, records in packet["records"].items():
            for record in records:
                number = record.get("invoice_number", "").translate(str.maketrans("", "", " -/"))
                self._db.execute("INSERT INTO records VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)", (
                    dataset, record.get("buyer_id", invoice["buyer_id"]), record.get("supplier_id", invoice["supplier_id"]),
                    record.get("id"), record.get("order_id", record.get("id") if dataset == "orders" else None),
                    record.get("requisition"), number, record.get("page"), json.dumps(record),
                ))
        self._db.commit()
        self._db.execute("PRAGMA query_only=ON")

    def select(self, dataset, **filters):
        if dataset not in ("suppliers", "orders", "receipts", "history", "pages"):
            raise ValueError("unknown source dataset")
        allowed = {"buyer_id", "supplier_id", "record_id", "order_id", "requisition", "invoice_key", "page"}
        if not set(filters) <= allowed:
            raise ValueError("unsupported source predicate")
        # Only allowlisted identifiers are formatted; every value is bound.
        predicates = "".join(f" AND {key} = ?" for key in filters)
        rows = self._db.execute("SELECT payload FROM records WHERE dataset = ?" + predicates, (dataset, *filters.values()))
        return [json.loads(row[0]) for row in rows]

    def close(self):
        self._db.close()

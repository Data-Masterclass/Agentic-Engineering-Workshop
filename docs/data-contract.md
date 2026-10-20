# Included data and fixture format

This repository contains only synthetic, freely redistributable data, authored for the workshop. All names/accounts are fictional. PDFs are one page; immutable page references use the full PDF SHA-256, a stable case/invoice ID and a 1-based page. PDF page observations were visually checked against rendered pages on 2026-10-14. Extraction fixture verification means the hash, original/candidate and intentional discrepancy were checked; it does **not** mean every extracted value is correct.

`schemas.py` defines strict invoice/line/page-reference, extraction, evidence, check, coverage and investigation contracts. Money and quantities serialize as decimal strings; floats are not needed. EUR money has cent precision, rounding is half up, units are `EA`, and the demonstration's tax rate is 19%. The seed uses stable `SUP-001`, `PO-001..003`, `L1`, `REC-001..002` and `HIST-001` IDs. IDs never authorize a lookup beyond the prepared packet.

| File/table | Required content |
|---|---|
| `data/invoices/<case>.pdf` | Redistributable source; stable case name from the allowlist |
| `data/extractions/<case>.json` | Extraction version/source/hash; identical original and initial candidate; typed fields/lines/page references |
| `data/observations/<case>.json` | Recorded observations with stable ID, exact page reference, field/value, confidence, excerpt and labelled origin |
| suppliers | case_id, id, name, bank_account, currency |
| purchase_orders | case_id, id, supplier_id, currency |
| po_lines | case_id, po_id, line_id, description, quantity, uom, unit_price |
| receipts | case_id, id, po_id, line_id, quantity, uom |
| invoice_history | case_id, id, supplier_id, invoice_number, gross, currency |
| coverage | case_id, dataset, status (`complete`/`selected`/`unavailable`), description including scope/as-of limitations |

Missing rows are not proof of absence: coverage explicitly records the scope and availability of each source. Fixture values preserve the original extraction, including intentional errors. Expected answers must stay outside runtime packets and model messages.

`python data/build_demo.py` deterministically regenerates all three PDFs and JSON fixtures (dev dependencies needed). Regeneration was verified to produce identical PDF hashes. `workshop seed` resets SQLite from `data/seed.sql`; every run uses parameterized queries against a fixed table allowlist. The database itself is generated in ignored `state/`, not committed. No business lookup tools are exposed in this exercise.

The missing-evidence page deliberately displays `[unreadable]`; this is an explicit unavailable field, not a difficult OCR benchmark. Its extraction candidate of 100 is unverified, receipt records are unavailable and complete duplicate scope is unavailable. Its PDF is still viewable; the required factual evidence is missing.

Session 1 keeps the raw packet and its source-completeness metadata with prepared validation, outside graph state. The investigation view contains extracted invoice/source identity, sanitized flagged checks/questions, actual PDF observations and accepted correction history. Local files under `Workshop Data/` are ignored by Git and are not part of the exercise fixtures; no automatic import or redistribution permission is implied.

## Session 4 supplier follow-up fixtures

Session 4 reuses the prepared Session 2 investigator and its selected-record
contract. It adds two one-page sources under `src/workshop/session2/assets/`:
`CP4-101` explicitly prints `[unreadable]` in the quantity cell, while `CP4-102`
prints quantity 10 and has selected accepted receipts for six units. The two
supplier-request scenarios share the same `CP4-101` invoice packet and PDF;
only the supplied correspondence differs. The posted-copy scenario reuses the
existing Session 2 fixture. Original Session 1 data and Session 2 PDF hashes are
preserved.

`src/workshop/session4/assets/correspondence.json` contains fictional sent and
received messages, a fixed selected scope/as-of, and a separately supplied
approved contact. It is a local fixture, not a mailbox connection. An empty or
unrelated selected thread does not establish complete correspondence history.
A promise to send a legible invoice is not a new readable invoice. Lookup
provenance and message references support a follow-up recommendation; they do
not clear invoice checks or authorize changes to source values.

Human review accepts or rejects the exact proposed draft for the local final
recommendation. No email is sent and no invoice is approved by that decision.

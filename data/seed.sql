-- Reproducible provisional synthetic Session 1 pack. No production data.
DROP TABLE IF EXISTS suppliers;
DROP TABLE IF EXISTS purchase_orders;
DROP TABLE IF EXISTS po_lines;
DROP TABLE IF EXISTS receipts;
DROP TABLE IF EXISTS invoice_history;
DROP TABLE IF EXISTS coverage;
CREATE TABLE suppliers(case_id TEXT, id TEXT, name TEXT, bank_account TEXT, currency TEXT);
CREATE TABLE purchase_orders(case_id TEXT, id TEXT, supplier_id TEXT, currency TEXT);
CREATE TABLE po_lines(case_id TEXT, po_id TEXT, line_id TEXT, description TEXT, quantity TEXT, uom TEXT, unit_price TEXT);
CREATE TABLE receipts(case_id TEXT, id TEXT, po_id TEXT, line_id TEXT, quantity TEXT, uom TEXT);
CREATE TABLE invoice_history(case_id TEXT, id TEXT, supplier_id TEXT, invoice_number TEXT, gross TEXT, currency TEXT);
CREATE TABLE coverage(case_id TEXT, dataset TEXT, status TEXT, description TEXT);
INSERT INTO suppliers VALUES
 ('matching','SUP-001','Synthetic Office Supply','DEMO-BANK-001','EUR'),
 ('reading-conflict','SUP-001','Synthetic Office Supply','DEMO-BANK-001','EUR'),
 ('missing-evidence','SUP-001','Synthetic Office Supply','DEMO-BANK-001','EUR');
INSERT INTO purchase_orders VALUES
 ('matching','PO-001','SUP-001','EUR'),
 ('reading-conflict','PO-002','SUP-001','EUR'),
 ('missing-evidence','PO-003','SUP-001','EUR');
INSERT INTO po_lines VALUES
 ('matching','PO-001','L1','Archive boxes','10','EA','12.00'),
 ('reading-conflict','PO-002','L1','Archive boxes','10','EA','12.00'),
 ('missing-evidence','PO-003','L1','Archive boxes','10','EA','12.00');
INSERT INTO receipts VALUES
 ('matching','REC-001','PO-001','L1','10','EA'),
 ('reading-conflict','REC-002','PO-002','L1','10','EA');
INSERT INTO invoice_history VALUES
 ('matching','HIST-001','SUP-001','OLD-001','60.00','EUR'),
 ('reading-conflict','HIST-001','SUP-001','OLD-001','60.00','EUR'),
 ('missing-evidence','HIST-001','SUP-001','OLD-001','60.00','EUR');
INSERT INTO coverage SELECT case_id,'supplier','selected','Only the selected supplier is supplied.' FROM suppliers;
INSERT INTO coverage SELECT case_id,'po','selected','Only the selected PO and its lines are supplied.' FROM suppliers;
INSERT INTO coverage SELECT case_id,'history','selected','Illustrative history only; global duplicate search is unavailable.' FROM suppliers;
INSERT INTO coverage VALUES
 ('matching','receipts','complete','All receipts for this selected PO/line as of 2026-10-01.'),
 ('reading-conflict','receipts','complete','All receipts for this selected PO/line as of 2026-10-01.'),
 ('missing-evidence','receipts','unavailable','Receipt records were not supplied.'),
 ('matching','duplicate_scope','complete','Prepared duplicate check is complete for this supplier/invoice number as of 2026-10-01.'),
 ('reading-conflict','duplicate_scope','complete','Prepared duplicate check is complete for this supplier/invoice number as of 2026-10-01.'),
 ('missing-evidence','duplicate_scope','unavailable','No complete duplicate check is available.');

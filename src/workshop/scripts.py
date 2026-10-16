"""Fixed teaching interactions. Never reads learner prompts or expected answers.
These responses demonstrate the transport contract, not a solution node.
"""
def interaction_examples(case):
    if case == "reading-conflict":
        return [
            {"tool_requests": [{"name": "review_pdf_page", "invoice_id": case, "page": 1}]},
            {"findings": {"evidence_ids": [case + ":page1:quantity"], "corrections": [{"field": "lines.L1.quantity", "value": "10", "evidence_id": case + ":page1:quantity"}], "note": "Fixed example: direct recorded page reading supports the proposed quantity."}},
        ]
    if case == "missing-evidence":
        return [
            {"tool_requests": [{"name": "review_pdf_page", "invoice_id": case, "page": 1}]},
            {"handoff": "Source quantity, complete receipt and duplicate evidence remain unavailable."},
        ]
    return []

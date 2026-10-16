"""Prepared correction/handoff behavior and the live PDF output contract."""
import copy
import json
import socket

import httpx
import pytest

from workshop.graph import Nodes
from workshop.pack import fixture, load_packet, observations, seed
from workshop.runtime import LiveClient, Runtime, ScriptedClient, Terminal
from workshop.scripts import interaction_examples


@pytest.fixture(autouse=True)
def offline(monkeypatch):
    monkeypatch.setattr(socket.socket, 'connect', lambda *_: pytest.fail('network forbidden'))


@pytest.mark.parametrize('case', ['reading-conflict', 'missing-evidence'])
def test_supported_findings_are_checked_before_handoff_without_more_inference(tmp_path, case):
    db = tmp_path / 'cases.sqlite'
    seed(db)
    # Use clear evidence in both cases; missing business coverage must stay unresolved.
    rows = [row.model_dump(mode='json') for row in observations('reading-conflict', 1)]
    for row in rows:
        row['page_ref'] = fixture(case).original.lines[0].page_ref.model_dump(mode='json')
    class Reader(ScriptedClient):
        def review(self, invoice, page):
            return copy.deepcopy(rows)
    runtime = Runtime(fixture(case), Reader())
    nodes = Nodes(runtime, lambda *_: pytest.fail('handoff must stop further inference'), packet=load_packet(case, db))
    state = {'candidate': fixture(case).candidate.model_dump(mode='json')}
    state.update(nodes.validation(state))
    request = {'name': 'review_pdf_page', 'invoice_id': case, 'page': 1}
    runtime.review(request)
    result = interaction_examples('reading-conflict')[1]
    result['handoff'] = 'Prepared validation must check the remaining business rules.'
    state.update(result=result, handoff=result['handoff'])
    assert nodes.route_investigation(state) == 'findings'
    state.update(nodes.findings(state))
    assert nodes.after_findings(state) == 'validate'
    state.update(nodes.validation(state))
    assert nodes.policy(state) == 'finalize'
    final = nodes.finalize(state)
    assert final['recommendation'] == ('READY_FOR_APPROVAL' if case == 'reading-conflict' else 'NEEDS_CLARIFICATION')
    assert state['candidate']['lines'][0]['quantity'] == '10'
    assert str(runtime.extraction.original.lines[0].quantity) == '100'
    assert len(runtime.history) == 1 and runtime.budget.models == 0
    assert sum(e['event'] == 'validation' for e in runtime.events) == 2


def test_handoff_does_not_execute_a_tool_or_override_terminal():
    runtime = Runtime(fixture('reading-conflict'))
    nodes = Nodes(runtime, lambda *_: None, packet={})
    request = interaction_examples('reading-conflict')[0]
    assert nodes.route_investigation({'result': request, 'handoff': 'Stop here'}) == 'finalize'
    result = interaction_examples('reading-conflict')[1]
    assert nodes.route_investigation({'result': result, 'handoff': 'Stop', 'terminal': 'Deadline'}) == 'finalize'
    assert runtime.budget.tools == runtime.budget.models == 0


@pytest.mark.parametrize('bad_field', ['L1.quantity', 'lines.UNKNOWN.quantity', 'supplier_id'])
def test_page_evidence_requires_an_exact_supported_field(bad_field):
    class Reader(ScriptedClient):
        def review(self, invoice, page):
            rows = [row.model_dump(mode='json') for row in observations(invoice, page)]
            rows[0]['field'] = bad_field
            return rows
    runtime = Runtime(fixture('reading-conflict'), Reader())
    with pytest.raises(Terminal, match='unsupported page evidence field'):
        runtime.review(interaction_examples('reading-conflict')[0]['tool_requests'][0])
    assert not runtime.evidence and not runtime.history


def test_pdf_reader_requests_a_strict_schema_with_exact_field_and_source(monkeypatch):
    import workshop.tools as tools
    monkeypatch.setattr(tools, 'page_image', lambda *_: b'test-png')
    for key, value in {'WORKSHOP_MODE':'live', 'WORKSHOP_LIVE_ACK':'approved-paid-calls',
                       'WORKSHOP_BASE_URL':'https://offline.invalid/v1', 'WORKSHOP_MODEL':'test',
                       'WORKSHOP_API_KEY':'SYNTHETIC', 'WORKSHOP_MAX_CALL_USD':'.01'}.items():
        monkeypatch.setenv(key, value)
    rows = [row.model_dump(mode='json') for row in observations('reading-conflict', 1)]
    for row in rows:
        row['origin'] = 'live-page-review'
    def endpoint(request):
        body = json.loads(request.content)
        form = body['text']['format']
        assert form['type'] == 'json_schema' and form['strict'] is True
        schema = form['schema']
        evidence = schema['$defs']['Evidence']['properties']
        assert evidence['field']['enum'] == ['lines.L1.quantity']
        assert evidence['origin']['enum'] == ['live-page-review']
        page = schema['$defs']['PageRef']['properties']
        assert page['invoice_id']['enum'] == ['reading-conflict']
        assert page['page']['enum'] == [1]
        assert page['sha256']['enum'] == [fixture('reading-conflict').invoice_sha256]
        return httpx.Response(200, json={'status':'completed', 'output':[
            {'type':'message', 'role':'assistant', 'content':[{'type':'output_text', 'text':json.dumps({'observations':rows})}]}]})
    client = LiveClient(transport=httpx.MockTransport(endpoint))
    records = client.review('reading-conflict', 1)
    assert records[0]['field'] == 'lines.L1.quantity'

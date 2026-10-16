"""Explicit checkpoint inputs and the native-tool/final-answer boundary."""
import json
import socket
import sys
from decimal import Decimal

import pytest

from workshop.agent import final_result_schema
from workshop.extraction import extract
from workshop.pack import fixture, observations, seed
from workshop.runtime import Budget, Runtime, ScriptedClient
from workshop.scripts import interaction_examples


@pytest.fixture(autouse=True)
def no_network(monkeypatch):
    def deny(*args, **kwargs):
        raise AssertionError("checkpoint contract tests must remain offline")
    monkeypatch.setattr(socket.socket, "connect", deny)


class FakeLive(ScriptedClient):
    live = True
    cost = Decimal('.01')

    def extract(self, case):
        raw = fixture(case).model_dump(mode='json')
        raw['source'] = 'live-vlm'
        for field in ('original', 'candidate'):
            raw[field]['lines'][0]['quantity'] = '10'
        return raw

    def review(self, case, page):
        rows = [e.model_dump(mode='json') for e in observations(case, page)]
        for row in rows:
            row['origin'] = 'live-page-review'
        return rows


def test_final_schema_cannot_request_a_tool_in_json():
    schema = final_result_schema()
    assert set(schema['properties']) == {'findings', 'handoff'}
    assert schema['additionalProperties'] is False
    assert 'tool_requests' not in json.dumps(schema) and 'ToolRequest' not in json.dumps(schema)


def test_runtime_supplies_only_the_final_answer_schema():
    class Capture(ScriptedClient):
        def investigation(self, messages):
            self.payload = json.loads(messages[1]['content'])
            return {'handoff': 'test only'}
    client = Capture()
    runtime = Runtime(fixture('reading-conflict'), client)
    runtime.ask('test', {'candidate': runtime.extraction.candidate.model_dump(mode='json')})
    assert client.payload['result_schema'] == final_result_schema()


def test_fixture_extraction_preserves_the_error_without_spending():
    class NoExtraction(FakeLive):
        def extract(self, case):
            raise AssertionError('explicit fixture input must not call extraction')
    result, remaining = extract('reading-conflict', NoExtraction(), Decimal('.25'), source='fixture')
    assert result.source == 'verified-fixture'
    assert str(result.original.lines[0].quantity) == '100'
    assert remaining == Decimal('.25')


def test_explicit_live_extraction_still_reserves_and_reads():
    result, remaining = extract('reading-conflict', FakeLive(), Decimal('.25'), source='live')
    assert result.source == 'live-vlm' and str(result.original.lines[0].quantity) == '10'
    assert remaining == Decimal('.24')


def test_live_extraction_is_not_an_offline_option():
    with pytest.raises(ValueError, match='live mode'):
        extract('reading-conflict', ScriptedClient(), Decimal('0'), source='live')


def test_failed_live_extraction_does_not_fall_back_to_fixture():
    class Broken(FakeLive):
        def extract(self, case):
            raise RuntimeError('simulated extraction failure')
    with pytest.raises(Exception, match='simulated extraction failure'):
        extract('reading-conflict', Broken(), Decimal('.25'), source='live')


@pytest.mark.parametrize('source', [None, 'live'])
def test_cli_checkpoint_defaults_to_fixture_and_keeps_live_opt_in(tmp_path, monkeypatch, source):
    from workshop import cli
    monkeypatch.setattr(cli, 'DB', tmp_path / 'checkpoint.sqlite')
    monkeypatch.setattr(cli, 'STATE', tmp_path)
    seed(cli.DB)
    monkeypatch.setenv('WORKSHOP_MODE', 'live')
    monkeypatch.setenv('WORKSHOP_SPEND_USD', '.25')
    monkeypatch.setattr(cli, 'LiveClient', lambda: FakeLive(interaction_examples('reading-conflict')))
    argv = ['workshop', 'run', '--case', 'reading-conflict']
    if source:
        argv += ['--extraction-source', source]
    monkeypatch.setattr(sys, 'argv', argv)
    cli.main()
    report = json.loads((tmp_path / 'reading-conflict/review.json').read_text())
    assert report['extraction']['source'] == ('live-vlm' if source else 'verified-fixture')
    assert report['extraction']['original']['lines'][0]['quantity'] == ('10' if source else '100')

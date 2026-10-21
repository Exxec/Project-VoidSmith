from __future__ import annotations

import io
import json
import unittest
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from starsector_variant_generator import api
from starsector_variant_generator.campaign.catalog import CommodityCatalog
from starsector_variant_generator.campaign.edit_plan import EditRequest
from starsector_variant_generator.campaign.fingerprint import (
    EXPECTED_FILE,
    build_expected,
    fnv64,
    hundredths,
    parse_probe_log,
    verify_ingame,
)
from starsector_variant_generator.cli import main as cli_main

try:
    from test_campaign_edit_plan import synthetic_save
    from test_campaign_writer import EXTRA_STACKS
except ImportError:  # run as tests.test_campaign_fingerprint
    from tests.test_campaign_edit_plan import synthetic_save
    from tests.test_campaign_writer import EXTRA_STACKS

CATALOG = CommodityCatalog('PARSED', frozenset({'supplies', 'fuel', 'crew', 'marines', 'heavy_machinery'}), (('synthetic.csv', 'neutral'),))
# Supplies 7 -> 40 on the fixture (capacities 100/200/300, stored space used 10, fuel 50, crew 100).
CARGO_TEXT = 'mC=10000;mF=20000;mP=30000;spaceUsed=1000;fuel=5000;crew=100;supplies=4000'
CARGO_FNV = 'a6d4a90f1e25f0be'
DIGEST = '0123456789abcdef'


def log_line(phase: str, section: str, digest: str, extra: str = '') -> str:
    return f'12:00:00 BF-PROBE|0.9|fingerprint|INFO|phase={phase}|section={section};count=1;len=9;fnv={digest}{extra}\n'


class HashTests(unittest.TestCase):
    def test_fnv_matches_the_probe_java_implementation(self):
        # Outputs of FingerprintSections.fnv64 compiled and run on the rig JDK (25.0.4.1+1), 2026-10-20.
        vectors = {
            '': 'cbf29ce484222325',
            'a': '089be207b544f1e4',
            'mC=10000;mF=20000;mP=30000': '5173cad1cfde1ae0',
            CARGO_TEXT: CARGO_FNV,
            'café €\U0001F600': '2887e54d18d2904f',
        }
        for text, digest in vectors.items():
            self.assertEqual(fnv64(text), digest, text)

    def test_hundredths_matches_java_float_rounding(self):
        # Math.round(Float.parseFloat(s) * 100f) on the rig JDK; ties and float32 effects included.
        java = {'7.0': '700', '0.005': '1', '0.015': '2', '1.005': '101', '2.675': '268', '16777217': '1677721600',
                '123456.789': '12345679', '0.1': '10', '1.0E10': '2147483647'}
        for text, expected in java.items():
            self.assertEqual(hundredths(text), expected, text)

    def test_value_beyond_float32_is_not_reproduced(self):
        self.assertIsNone(hundredths('3.4028234663852886E38'))


class ExpectedFingerprintTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.folder = synthetic_save(self.root / 'save', duplicate=EXTRA_STACKS)
        path = self.folder / 'campaign.xml'
        path.write_text(path.read_text(encoding='utf-8').replace('sU="7.0"', 'sU="10.0"'), encoding='utf-8')
        self.out = self.root / 'out'

    def write(self, *edits):
        plan = api.run_save_edit_plan(self.folder, tuple(EditRequest(t, v) for t, v in edits), CATALOG)
        result = api.run_save_edit_write(plan, self.out)
        self.assertEqual(result.status, 'WRITTEN', result.reason)
        return plan, Path(result.copy_dir)

    def expected(self, copy):
        return json.loads((copy / EXPECTED_FILE).read_text(encoding='utf-8'))

    def test_workshop_writes_expectation_for_cargo_and_still_reverifies(self):
        plan, copy = self.write(('commodity:supplies', 40))
        document = self.expected(copy)
        cargo = document['sections']['cargo']
        self.assertEqual((cargo['text'], cargo['fnv'], cargo['count'], cargo['len']), (CARGO_TEXT, CARGO_FNV, 1, len(CARGO_TEXT)))
        self.assertEqual(document['intentionally_changed'], ['cargo'])
        self.assertNotIn('cargo', document['must_leave_unchanged'])
        self.assertIn('player', document['must_leave_unchanged'])
        self.assertIn('player', document['not_covered'])
        self.assertEqual(cargo['edited_capacity_fields'], [])
        # supplies +33 at 1 space each: a load that recomputes space used from the edit would report 43.
        self.assertEqual(cargo['variants']['space_used_recomputed_by_delta']['text'], CARGO_TEXT.replace('spaceUsed=1000', 'spaceUsed=4300'))
        self.assertEqual(api.run_save_verify_copy(plan, copy).status, 'VERIFIED')
        self.assertFalse((self.folder / EXPECTED_FILE).exists())

    def test_credit_only_edit_leaves_cargo_unchanged_but_still_expected(self):
        _plan, copy = self.write(('credits', 250))
        document = self.expected(copy)
        self.assertEqual(document['intentionally_changed'], [])
        self.assertEqual(document['sections']['cargo']['text'], CARGO_TEXT.replace('supplies=4000', 'supplies=700'))

    def test_cargo_excluded_when_a_figure_is_missing_or_crew_is_fractional(self):
        path = self.folder / 'campaign.xml'
        original = path.read_text(encoding='utf-8')
        for old, new in (('sU="10.0"', ''), ('s="100.0" mS="1000000.0" cSPU="0.0"><d cl="st">crew', 's="100.5" mS="1000000.0" cSPU="0.0"><d cl="st">crew')):
            path.write_text(original.replace(old, new), encoding='utf-8')
            plan = api.run_save_edit_plan(self.folder, (EditRequest('credits', 250),), CATALOG)
            document = build_expected(self.folder, self.folder, plan)
            self.assertNotIn('cargo', document['sections'], old)
            self.assertIn('cargo', document['not_covered'])

    def test_edited_capacity_gets_a_source_variant(self):
        plan, copy = self.write(('commodity:supplies', 40))
        path = copy / 'campaign.xml'
        path.write_text(path.read_text(encoding='utf-8').replace('mC="100.0"', 'mC="150.0"'), encoding='utf-8')
        cargo = build_expected(self.folder, copy, plan)['sections']['cargo']
        self.assertEqual(cargo['edited_capacity_fields'], ['mC'])
        self.assertIn('mC=15000', cargo['text'])
        self.assertIn('mC=10000', cargo['variants']['capacity_as_source']['text'])


class VerifyInGameTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.folder = synthetic_save(self.root / 'save', duplicate=EXTRA_STACKS)
        path = self.folder / 'campaign.xml'
        path.write_text(path.read_text(encoding='utf-8').replace('sU="7.0"', 'sU="10.0"'), encoding='utf-8')
        plan = api.run_save_edit_plan(self.folder, (EditRequest('commodity:supplies', 40),), CATALOG)
        self.copy = Path(api.run_save_edit_write(plan, self.root / 'out').copy_dir)
        self.plan = plan
        self.variant = self.expected()['sections']['cargo']['variants']['space_used_recomputed_by_delta']['fnv']

    def expected(self):
        return json.loads((self.copy / EXPECTED_FILE).read_text(encoding='utf-8'))

    def verify(self, *lines):
        log = self.root / 'probe.log'
        log.write_text('noise\n' + ''.join(lines), encoding='utf-8')
        return verify_ingame(self.copy, log)

    def untouched(self, digest_after=DIGEST, skip=()):
        lines = []
        for section in ('markets', 'systems', 'rings', 'fleets', 'player', 'mod', 'totals'):
            if section not in skip:
                lines.append(log_line('before', section, DIGEST, ';source=file'))
                lines.append(log_line('after', section, digest_after if section == 'player' else DIGEST))
        return lines

    def statuses(self, report):
        return {row['section']: row['status'] for row in report['sections']}

    def test_everything_matches(self):
        report = self.verify(log_line('after', 'cargo', CARGO_FNV), *self.untouched())
        self.assertEqual(report['verdict'], 'PASS')
        self.assertEqual(set(self.statuses(report).values()), {'MATCH'})
        self.assertEqual(report['capacity']['result'], 'NOT_EXERCISED')

    def test_recomputed_space_used_is_reported_and_needs_review(self):
        report = self.verify(log_line('after', 'cargo', self.variant), *self.untouched())
        cargo = next(r for r in report['sections'] if r['section'] == 'cargo')
        self.assertEqual((report['verdict'], cargo['status'], cargo['matched_variant']), ('REVIEW', 'DIFFERS', 'space_used_recomputed_by_delta'))

    def test_unrelated_cargo_digest_differs(self):
        report = self.verify(log_line('after', 'cargo', DIGEST), *self.untouched())
        self.assertEqual((report['verdict'], self.statuses(report)['cargo']), ('REVIEW', 'DIFFERS'))

    def test_section_missing_from_log_is_reported(self):
        report = self.verify(*self.untouched(skip=('totals',)))
        statuses = self.statuses(report)
        self.assertEqual((statuses['cargo'], statuses['totals'], report['verdict']), ('NOT_IN_LOG', 'NOT_IN_LOG', 'REVIEW'))

    def test_an_untouched_section_that_changed_fails(self):
        report = self.verify(log_line('after', 'cargo', CARGO_FNV), *self.untouched(digest_after='ffffffffffffffff'))
        self.assertEqual((report['verdict'], self.statuses(report)['player']), ('FAIL', 'DIFFERS'))

    def test_log_without_after_lines_fails(self):
        report = self.verify(log_line('before', 'cargo', CARGO_FNV))
        self.assertEqual((report['verdict'], report['sections']), ('FAIL', []))

    def test_stored_file_digest_wins_over_the_pre_save_one(self):
        before, after = parse_probe_log(log_line('before', 'player', '1' * 16) + log_line('before', 'player', '2' * 16, ';source=file')
                                        + log_line('after', 'player', '3' * 16))
        self.assertEqual((before['player'], after['player']), ('2' * 16, '3' * 16))

    def test_capacity_recompute_is_decided_from_an_edited_capacity(self):
        path = self.copy / 'campaign.xml'
        path.write_text(path.read_text(encoding='utf-8').replace('mC="100.0"', 'mC="150.0"'), encoding='utf-8')
        document = build_expected(self.folder, self.copy, self.plan)
        (self.copy / EXPECTED_FILE).write_text(json.dumps(document), encoding='utf-8')
        kept = self.verify(log_line('after', 'cargo', document['sections']['cargo']['fnv']), *self.untouched())
        self.assertEqual(kept['capacity']['result'], 'KEPT')
        recomputed = self.verify(log_line('after', 'cargo', document['sections']['cargo']['variants']['capacity_as_source']['fnv']), *self.untouched())
        self.assertEqual((recomputed['capacity']['result'], recomputed['verdict']), ('RECOMPUTED', 'REVIEW'))

    def run_cli(self, log_text):
        log = self.root / 'cli.log'
        log.write_text(log_text, encoding='utf-8')
        argv = ['voidsmith', 'save', 'verify-ingame', str(self.copy), str(log)]
        with patch('sys.argv', argv), redirect_stdout(io.StringIO()) as captured:
            code = cli_main.main()
        return code, json.loads(captured.getvalue())

    def test_cli_exit_codes_follow_check_mod(self):
        passing = log_line('after', 'cargo', CARGO_FNV) + ''.join(self.untouched())
        self.assertEqual(self.run_cli(passing)[0], 0)
        self.assertEqual(self.run_cli(log_line('after', 'cargo', DIGEST) + ''.join(self.untouched()))[0], 1)
        self.assertEqual(self.run_cli('nothing here\n')[0], 2)

    def test_cli_rejects_a_folder_without_an_expectation(self):
        (self.copy / EXPECTED_FILE).unlink()
        log = self.root / 'x.log'
        log.write_text('x', encoding='utf-8')
        with patch('sys.argv', ['voidsmith', 'save', 'verify-ingame', str(self.copy), str(log)]), \
                redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()), self.assertRaises(SystemExit) as raised:
            cli_main.main()
        self.assertEqual(raised.exception.code, 2)


if __name__ == '__main__':
    unittest.main()

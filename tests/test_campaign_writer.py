from __future__ import annotations

import io
import json
import os
import unittest
from contextlib import redirect_stdout
from dataclasses import replace
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from starsector_variant_generator import api
from starsector_variant_generator.campaign import writer as writer_module
from starsector_variant_generator.campaign.catalog import CommodityCatalog
from starsector_variant_generator.campaign.edit_plan import EditRequest
from starsector_variant_generator.campaign.verify import VerificationReport, verify_copy

try:
    from test_campaign_edit_plan import source_hashes, synthetic_save
except ImportError:  # run as tests.test_campaign_writer
    from tests.test_campaign_edit_plan import source_hashes, synthetic_save

CATALOG = CommodityCatalog('PARSED', frozenset({'supplies', 'fuel', 'crew', 'marines', 'heavy_machinery'}), (('synthetic.csv', 'neutral'),))
# The base fixture holds supplies 7.0 (1 space each); capacities: cargo 100, fuel 200, personnel 300; space used 7.
EXTRA_STACKS = (
    '<CIStack t="RESOURCES" s="50.0" mS="1000000.0" cSPU="0.0"><d cl="st">fuel</d></CIStack>'
    '<CIStack t="RESOURCES" s="100.0" mS="1000000.0" cSPU="0.0"><d cl="st">crew</d></CIStack>'
    '<CIStack t="RESOURCES" s="20.0" mS="1000000.0" cSPU="0.0"><d cl="st">marines</d></CIStack>'
    '<CIStack t="RESOURCES" s="3.0" mS="1000000.0" cSPU="1.0"><d cl="st">heavy_machinery</d></CIStack>'
)


class SaveWriterTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.folder = synthetic_save(self.root / 'save', duplicate=EXTRA_STACKS)
        # The fixture's space used (7) counts supplies only; with the 3 heavy machinery added it is 10.
        path = self.folder / 'campaign.xml'
        path.write_text(path.read_text(encoding='utf-8').replace('sU="7.0"', 'sU="10.0"'), encoding='utf-8')
        self.out = self.root / 'out'

    def plan(self, *edits, **options):
        return api.run_save_edit_plan(self.folder, tuple(EditRequest(t, v) for t, v in edits), CATALOG, **options)

    def write(self, *edits, name=None, **options):
        return api.run_save_edit_write(self.plan(*edits, **options), self.out, name=name)

    def reread(self, folder):
        return {r.target: r.value for r in api.run_save_resources(folder).resources}

    # --- the happy path and what must hold after every operation -------------------------------------------

    def test_writes_verified_copy_with_only_planned_values_changed(self):
        before = source_hashes(self.folder)
        result = self.write(('credits', 250), ('commodity:supplies', 40), ('story_points', 5))
        self.assertEqual(result.status, 'WRITTEN', result.reason)
        copy = Path(result.copy_dir)
        self.assertEqual(copy.parent, self.out / 'save_workshop')
        self.assertEqual(result.verification.status, 'VERIFIED')
        self.assertTrue(result.verification.only_planned_spans_differ)
        values = self.reread(copy)
        self.assertEqual((values['credits'], values['commodity:supplies'], values['story_points']), ('250.0', '40.0', '5'))
        original = self.reread(self.folder)
        for target in ('commodity:fuel', 'commodity:crew', 'commodity:marines', 'commodity:heavy_machinery'):
            self.assertEqual(values[target], original[target])
        self.assertEqual(source_hashes(self.folder), before)
        self.assertEqual((copy / 'descriptor.xml').read_bytes(), (self.folder / 'descriptor.xml').read_bytes())
        self.assertIn('NOT been loaded', ' '.join(result.notes))
        json.dumps(result.to_payload())

    def test_replacements_of_different_length_keep_every_other_byte_and_utf8(self):
        original = (self.folder / 'campaign.xml').read_bytes()
        result = self.write(('credits', 5), ('commodity:supplies', 97), ('story_points', 1234567))
        self.assertEqual(result.status, 'WRITTEN', result.reason)
        copy = (Path(result.copy_dir) / 'campaign.xml').read_bytes()
        self.assertIn('évidence'.encode(), copy)
        expected = original
        for old, new in ((b'<value>120.0</value>', b'<value>5.0</value>'), (b's="7.0" mS', b's="97.0" mS'), (b'sp="2"', b'sp="1234567"')):
            self.assertEqual(expected.count(old), 1)
            expected = expected.replace(old, new)
        self.assertEqual(copy, expected)

    def test_no_change_request_refused_and_nothing_written(self):
        result = self.write(('credits', 120))
        self.assertEqual(result.status, 'REFUSED')
        self.assertIn('nothing to write', result.reason)
        self.assertFalse(self.out.exists())

    # --- refusals: nothing is created -----------------------------------------------------------------------

    def test_over_capacity_refused_even_with_plan_opt_in(self):
        before = source_hashes(self.folder)
        for options in ({}, {'allow_unknown_capacity': True}):
            with self.subTest(options=options):
                result = self.write(('commodity:supplies', 101), **options)
                self.assertEqual(result.status, 'REFUSED')
                self.assertIn('NOT_DETERMINABLE', result.reason)
        self.assertFalse(self.out.exists())
        self.assertEqual(source_hashes(self.folder), before)

    def test_refused_and_duplicate_changes_block_the_whole_write(self):
        for edits in ((('credits', -1),), (('credits', 5), ('credits', 6)), (('credits', 5), ('commodity:neutral_ore', 1))):
            with self.subTest(edits=edits):
                self.assertEqual(self.write(*edits).status, 'REFUSED')
        self.assertFalse(self.out.exists())

    def test_target_exists_is_never_overwritten(self):
        first = self.write(('credits', 250), name='copy_one')
        self.assertEqual(first.status, 'WRITTEN')
        marker = Path(first.copy_dir) / 'campaign.xml'
        before = marker.read_bytes()
        second = self.write(('credits', 300), name='copy_one')
        self.assertEqual(second.status, 'REFUSED')
        self.assertIn('already exists', second.reason)
        self.assertEqual(marker.read_bytes(), before)

    def test_source_changed_after_planning_refused(self):
        plan = self.plan(('credits', 250))
        path = self.folder / 'campaign.xml'
        path.write_text(path.read_text(encoding='utf-8').replace('<unknown>', '<unknown> '), encoding='utf-8')
        result = api.run_save_edit_write(plan, self.out)
        self.assertEqual(result.status, 'REFUSED')
        self.assertIn('SOURCE_CHANGED', result.reason)
        self.assertFalse(self.out.exists())

    def test_gate_mismatch_and_empty_plan_refused(self):
        plan = self.plan(('credits', 250))
        self.assertEqual(api.run_save_edit_write(replace(plan, write_gate_status='CLOSED_CAPACITY_EVIDENCE'), self.out).status, 'REFUSED')
        self.assertEqual(api.run_save_edit_write(replace(plan, changes=()), self.out).status, 'REFUSED')
        self.assertFalse(self.out.exists())

    def test_output_directory_rules(self):
        plan = self.plan(('credits', 250))
        for bad in (self.folder, self.folder / 'inside', self.root, self.folder.parent / '..' / 'x'):
            with self.subTest(output=str(bad)):
                self.assertEqual(api.run_save_edit_write(plan, bad).status, 'REFUSED')
        for name in ('', '.hidden', '../up', 'a/b', 'x' * 121, 'bad name'):
            with self.subTest(name=name):
                self.assertEqual(api.run_save_edit_write(plan, self.out, name=name).status, 'REFUSED')
        self.assertFalse((self.folder / 'inside').exists())
        self.assertFalse(self.out.exists())

    def test_linked_output_directory_refused(self):
        real = self.root / 'real'
        real.mkdir()
        link = self.root / 'link'
        try:
            os.symlink(real, link, target_is_directory=True)
        except (OSError, NotImplementedError):
            self.skipTest('symlinks unavailable on this system')
        self.assertEqual(api.run_save_edit_write(self.plan(('credits', 250)), link).status, 'REFUSED')
        self.assertEqual(list(real.iterdir()), [])

    def test_unflat_save_folder_refused(self):
        plan = self.plan(('credits', 250))
        (self.folder / 'extra').mkdir()
        result = api.run_save_edit_write(plan, self.out)
        self.assertEqual(result.status, 'REFUSED')
        self.assertFalse(self.out.exists())

    def test_default_name_is_deterministic_and_plan_specific(self):
        a, b = self.plan(('credits', 250)), self.plan(('credits', 251))
        self.assertEqual(writer_module.default_copy_name(a), writer_module.default_copy_name(self.plan(('credits', 250))))
        self.assertNotEqual(writer_module.default_copy_name(a), writer_module.default_copy_name(b))

    # --- failure handling -----------------------------------------------------------------------------------

    def test_failed_verification_removes_the_copy(self):
        failed = VerificationReport('FAILED', True, False, True, (), ('forced',))
        with patch.object(writer_module, 'verify_copy', return_value=failed):
            result = self.write(('credits', 250), name='doomed')
        self.assertEqual(result.status, 'FAILED_VERIFICATION')
        self.assertIsNone(result.copy_dir)
        self.assertFalse((self.out / 'save_workshop' / 'doomed').exists())

    def test_failed_verification_removes_the_copy_when_the_output_dir_is_an_8_3_alias(self):
        try:
            from test_safeio import short_alias
        except ImportError:  # run as tests.test_campaign_writer
            from tests.test_safeio import short_alias
        long_out = self.root / 'a rather long output folder'
        long_out.mkdir()
        alias = short_alias(long_out)
        if alias is None:
            self.skipTest('8.3 short names are unavailable here')
        failed = VerificationReport('FAILED', True, False, True, (), ('forced',))
        with patch.object(writer_module, 'verify_copy', return_value=failed):
            result = api.run_save_edit_write(self.plan(('credits', 250)), alias, name='doomed')
        self.assertEqual(result.status, 'FAILED_VERIFICATION')
        self.assertFalse((long_out / 'save_workshop' / 'doomed').exists())

    def test_unexpected_error_removes_the_copy(self):
        with patch.object(writer_module, 'verify_copy', side_effect=RuntimeError('boom')):
            result = self.write(('credits', 250), name='doomed')
        self.assertEqual(result.status, 'FAILED')
        self.assertFalse((self.out / 'save_workshop' / 'doomed').exists())

    # --- the verifier does not trust the writer -------------------------------------------------------------

    def tampered(self, mutate):
        plan = self.plan(('credits', 250), ('commodity:supplies', 40))
        result = api.run_save_edit_write(plan, self.out, name='tamper')
        self.assertEqual(result.status, 'WRITTEN')
        copy = Path(result.copy_dir)
        originals = {n: h for n, h in source_hashes(self.folder).items()}
        mutate(copy)
        return verify_copy(self.folder, copy, plan, originals)

    def test_verifier_flags_unplanned_byte_changes(self):
        def mutate(copy):
            path = copy / 'campaign.xml'
            path.write_bytes(path.read_bytes().replace(b'<unknown>', b'<Unknown>'))
        report = self.tampered(mutate)
        self.assertEqual(report.status, 'FAILED')
        self.assertFalse(report.only_planned_spans_differ)

    def test_verifier_flags_wrong_planned_value_other_files_and_extras(self):
        cases = {
            'wrong planned value': lambda c: (c / 'campaign.xml').write_bytes((c / 'campaign.xml').read_bytes().replace(b'<value>250.0<', b'<value>251.0<')),
            'descriptor edited': lambda c: (c / 'descriptor.xml').write_text((c / 'descriptor.xml').read_text() + ' '),
            'extra file': lambda c: (c / 'extra.bak').write_text('x'),
        }
        for label, mutate in cases.items():
            with self.subTest(label):
                folder = synthetic_save(self.root / ('s_' + label.replace(' ', '_')), duplicate=EXTRA_STACKS)
                plan = api.run_save_edit_plan(folder, (EditRequest('credits', 250),), CATALOG)
                result = api.run_save_edit_write(plan, self.root / ('o_' + label.replace(' ', '_')), name='t')
                copy = Path(result.copy_dir)
                mutate(copy)
                report = verify_copy(folder, copy, plan, source_hashes(folder))
                self.assertEqual(report.status, 'FAILED', label)

    def test_verifier_flags_a_changed_original(self):
        def mutate(_copy):
            path = self.folder / 'descriptor.xml'
            path.write_text(path.read_text(encoding='utf-8') + ' ', encoding='utf-8')
        report = self.tampered(mutate)
        self.assertFalse(report.original_unchanged)
        self.assertEqual(report.status, 'FAILED')

    # --- capacity rules by dimension ------------------------------------------------------------------------

    def outcome(self, *edits):
        plan = self.plan(*edits)
        return tuple(c.outcome for c in plan.changes)

    def test_fuel_capacity(self):
        self.assertEqual(self.outcome(('commodity:fuel', 200)), ('ACCEPTED',))
        self.assertEqual(self.outcome(('commodity:fuel', 201)), ('NOT_DETERMINABLE',))

    def test_personnel_counts_crew_plus_marines(self):
        self.assertEqual(self.outcome(('commodity:crew', 280)), ('ACCEPTED',))   # 280 + 20 marines = 300
        self.assertEqual(self.outcome(('commodity:crew', 281)), ('NOT_DETERMINABLE',))
        self.assertEqual(self.outcome(('commodity:marines', 200), ('commodity:crew', 100)), ('ACCEPTED', 'ACCEPTED'))
        self.assertEqual(self.outcome(('commodity:marines', 200), ('commodity:crew', 101)), ('NOT_DETERMINABLE', 'NOT_DETERMINABLE'))
        # a request equal to the saved value is not a change, so it stays ACCEPTED beside an over-capacity one
        self.assertEqual(self.outcome(('commodity:marines', 201), ('commodity:crew', 100)), ('NOT_DETERMINABLE', 'ACCEPTED'))

    def test_cargo_is_judged_across_all_edited_cargo_stacks(self):
        # used 10 (7 supplies + 3 machinery): each alone fits, together they do not.
        self.assertEqual(self.outcome(('commodity:supplies', 97)), ('ACCEPTED',))
        self.assertEqual(self.outcome(('commodity:heavy_machinery', 93)), ('ACCEPTED',))
        self.assertEqual(self.outcome(('commodity:supplies', 97), ('commodity:heavy_machinery', 93)), ('NOT_DETERMINABLE',) * 2)
        self.assertEqual(self.outcome(('commodity:supplies', 98)), ('NOT_DETERMINABLE',))
        # lowering one stack frees space for raising another
        self.assertEqual(self.outcome(('commodity:supplies', 0), ('commodity:heavy_machinery', 100)), ('ACCEPTED', 'ACCEPTED'))

    def test_dimensions_are_independent_and_unprovable_capacity_is_not_determinable(self):
        self.assertEqual(self.outcome(('commodity:fuel', 201), ('commodity:supplies', 10)), ('NOT_DETERMINABLE', 'ACCEPTED'))
        text = (self.folder / 'campaign.xml').read_text(encoding='utf-8')
        for label, old, new in (('no fuel capacity', ' mF="200.0"', ''), ('no space used', ' sU="10.0"', ''),
                                ('no personnel capacity', ' mP="300.0"', ''), ('no space per unit', ' cSPU="1.0"><d cl="st">supplies', '><d cl="st">supplies')):
            with self.subTest(label):
                (self.folder / 'campaign.xml').write_text(text.replace(old, new, 1), encoding='utf-8')
                edit = ('commodity:fuel', 10) if 'fuel' in label else ('commodity:crew', 10) if 'personnel' in label else ('commodity:supplies', 10)
                self.assertEqual(self.outcome(edit), ('NOT_DETERMINABLE',))

    def test_decrease_that_stays_over_capacity_is_not_accepted(self):
        (self.folder / 'campaign.xml').write_text((self.folder / 'campaign.xml').read_text(encoding='utf-8').replace('sU="10.0"', 'sU="150.0"'), encoding='utf-8')
        self.assertEqual(self.outcome(('commodity:supplies', 5)), ('NOT_DETERMINABLE',))  # 150 - 2 still above 100

    def test_space_used_below_what_the_stacks_occupy_is_unprovable(self):
        (self.folder / 'campaign.xml').write_text((self.folder / 'campaign.xml').read_text(encoding='utf-8').replace('sU="10.0"', 'sU="4.0"'), encoding='utf-8')
        self.assertEqual(self.outcome(('commodity:supplies', 10)), ('NOT_DETERMINABLE',))

    # --- command line ---------------------------------------------------------------------------------------

    def run_cli(self, *argv):
        from starsector_variant_generator.cli.main import main
        output = io.StringIO()
        with patch('sys.argv', ['voidsmith', *argv]), redirect_stdout(output):
            code = main()
        return code, json.loads(output.getvalue())

    def test_cli_write_succeeds_and_refuses_with_exit_codes(self):
        before = source_hashes(self.folder)
        with patch.object(api, 'run_save_commodity_catalog', return_value=CATALOG):
            code, payload = self.run_cli('save', 'write', str(self.folder), '--set', 'credits=300', '--set', 'commodity:supplies=20',
                                         '--starsector-path', str(self.root), '--output-dir', str(self.out), '--name', 'cli_copy')
            self.assertEqual((code, payload['write']['status']), (0, 'WRITTEN'))
            self.assertEqual(self.reread(self.out / 'save_workshop' / 'cli_copy')['credits'], '300.0')
            code, payload = self.run_cli('save', 'write', str(self.folder), '--set', 'commodity:supplies=500',
                                         '--starsector-path', str(self.root), '--output-dir', str(self.out), '--name', 'cli_over')
            self.assertEqual((code, payload['write']['status']), (1, 'REFUSED'))
        self.assertFalse((self.out / 'save_workshop' / 'cli_over').exists())
        self.assertEqual(source_hashes(self.folder), before)

    def test_cli_write_never_offers_the_over_capacity_opt_in(self):
        from starsector_variant_generator.cli.main import main
        argv = ['voidsmith', 'save', 'write', str(self.folder), '--set', 'credits=1', '--allow-unknown-capacity']
        with patch('sys.argv', argv), self.assertRaises(SystemExit):
            main()


if __name__ == '__main__':
    unittest.main()

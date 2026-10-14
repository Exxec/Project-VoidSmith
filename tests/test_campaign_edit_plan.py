from __future__ import annotations

import hashlib
import io
import json
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from starsector_variant_generator import api
from starsector_variant_generator.campaign.catalog import CommodityCatalog, read_commodity_catalog
from starsector_variant_generator.campaign.edit_plan import EditRequest
from starsector_variant_generator.campaign.format import inspect_save
from starsector_variant_generator.campaign.locators import locate_resources


def synthetic_save(folder: Path, *, partials="", duplicate="", person_ref=True):
    folder.mkdir()
    (folder / 'descriptor.xml').write_text('<SaveGameData><gameVersion>0.98a-RC8</gameVersion>'
        '<saveFileVersion>0.6</saveFileVersion><compressed>false</compressed></SaveGameData>', encoding='utf-8')
    person = '<person ref="9"/>' if person_ref else '<person z="9"><stats sp="2"/></person>'
    separate = '<neutralPerson z="9"><stats sp="2"/></neutralPerson>' if person_ref else ''
    campaign = f'''<?xml version="1.0" encoding="UTF-8"?>
<CampaignEngine><objects><neutralFleet z="2"><fD z="3"><cargo z="4" mC="100.0" mF="200.0" mP="300.0" sU="7.0">
<s z="5"><CIStack z="6" t="RESOURCES" s="7.0" mS="1000000.0" cSPU="1.0"><d cl="st">supplies</d><c ref="4"/></CIStack>{duplicate}</s>
<c z="7"><value>120.0</value></c><partials>{partials}</partials></cargo></fD></neutralFleet>
<neutralFleet z="8"><fD><cargo><c><value>999.0</value></c></cargo></fD></neutralFleet>{separate}</objects>
<playerFleet ref="2"/><characterData z="10">{person}</characterData><unknown>évidence</unknown></CampaignEngine>'''
    (folder / 'campaign.xml').write_text(campaign, encoding='utf-8')
    return folder


def source_hashes(folder):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in folder.iterdir()}


class CampaignEditPlanTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)
        self.folder = synthetic_save(self.root / 'save')
        self.catalog = CommodityCatalog('PARSED', frozenset({'supplies'}), (('synthetic.csv', 'neutral'),))

    def snapshot(self):
        return api.run_save_resources(self.folder)

    def plan(self, target='credits', value=250, **options):
        return api.run_save_edit_plan(self.folder, (EditRequest(target, value),), self.catalog, **options)

    def test_locators_resolve_only_player_and_exact_utf8_byte_spans(self):
        before = source_hashes(self.folder)
        snapshot = self.snapshot()
        self.assertEqual(snapshot.status, 'READABLE')
        resources = {r.target: r for r in snapshot.resources}
        self.assertEqual(resources['credits'].value, '120.0')
        self.assertEqual(resources['story_points'].value, '2')
        self.assertEqual(resources['commodity:supplies'].value, '7.0')
        self.assertEqual(dict(snapshot.capacities)['cargo'], '100.0')
        raw = (self.folder / 'campaign.xml').read_bytes()
        for resource in snapshot.resources:
            loc = resource.locator
            self.assertEqual(raw[loc.start:loc.end].decode('ascii'), loc.original)
        self.assertEqual(source_hashes(self.folder), before)

    def test_credit_and_story_plans_are_pure_and_write_gate_is_within_capacity_only(self):
        before = source_hashes(self.folder)
        for target in ('credits', 'story_points'):
            with self.subTest(target=target):
                plan = self.plan(target, 300)
                self.assertEqual(plan.changes[0].outcome, 'ACCEPTED')
                self.assertTrue(plan.ready_for_copy)
                self.assertEqual(plan.write_gate_status, 'OPEN_WITHIN_CAPACITY')
                json.dumps(plan.to_payload())
        self.assertEqual(source_hashes(self.folder), before)

    def test_non_integer_negative_and_bool_requests_refused(self):
        for value in (-1, 1.5, True, '2'):
            with self.subTest(value=value):
                plan = self.plan(value=value)
                self.assertEqual(plan.changes[0].outcome, 'REFUSED')
                self.assertFalse(plan.ready_for_copy)

    def test_stored_type_bounds_and_float_precision(self):
        for target, value in [('story_points', 2**31), ('credits', 16777217), ('credits', 10**400)]:
            with self.subTest(target=target, value=value):
                self.assertEqual(self.plan(target, value).changes[0].outcome, 'REFUSED')
        self.assertEqual(self.plan('credits', 16777218).changes[0].outcome, 'ACCEPTED')
        self.assertEqual(self.plan('story_points', 2**31-1).changes[0].outcome, 'ACCEPTED')

    def test_noop_preserves_original_number_bytes(self):
        plan = self.plan(value=120)
        self.assertEqual(plan.changes[0].replacement, '120.0')
        plan = self.plan('commodity:supplies', 7)
        self.assertEqual(plan.changes[0].outcome, 'ACCEPTED')

    def test_commodity_requires_installed_membership(self):
        plan = api.run_save_edit_plan(self.folder, (EditRequest('commodity:supplies', 10),))
        self.assertEqual(plan.changes[0].outcome, 'REFUSED')

    def test_commodity_within_saved_capacity_is_accepted_and_overage_needs_opt_in(self):
        for quantity in (10, 100):  # saved space used 7 of 100: 10 and exactly-at-capacity both fit
            with self.subTest(quantity=quantity):
                plan = self.plan('commodity:supplies', quantity)
                self.assertEqual(plan.changes[0].outcome, 'ACCEPTED')
                self.assertTrue(plan.ready_for_copy)
        plan = self.plan('commodity:supplies', 101)
        self.assertEqual(plan.changes[0].outcome, 'NOT_DETERMINABLE')
        self.assertFalse(plan.ready_for_copy)
        plan = self.plan('commodity:supplies', 101, allow_unknown_capacity=True)
        self.assertEqual(plan.changes[0].outcome, 'NOT_DETERMINABLE')
        self.assertTrue(plan.changes[0].capacity_opt_in)
        self.assertTrue(plan.ready_for_copy)  # planning opt-in only; the writer still refuses (see test_campaign_writer)
        self.assertEqual(plan.write_gate_status, 'OPEN_WITHIN_CAPACITY')

    def test_opt_in_does_not_bypass_any_hard_refusal(self):
        plan = self.plan('commodity:supplies', 1000001, allow_unknown_capacity=True)
        self.assertEqual(plan.changes[0].outcome, 'REFUSED')
        self.assertFalse(plan.ready_for_copy)

    def test_missing_stacks_and_out_of_tier_targets_refused(self):
        for target in ('commodity:fuel', 'commodity:neutral_ore', 'officer_skills', '../credits'):
            self.assertEqual(self.plan(target, 20).changes[0].outcome, 'REFUSED')

    def test_duplicate_requests_refused(self):
        plan = api.run_save_edit_plan(self.folder, (EditRequest('credits', 5), EditRequest('credits', 6)))
        self.assertFalse(plan.ready_for_copy)
        self.assertTrue(all(change.outcome == 'REFUSED' for change in plan.changes))

    def test_refused_input_and_empty_plan(self):
        with self.assertRaises(ValueError):
            api.run_save_edit_plan(self.folder, ())
        with self.assertRaises(ValueError):
            self.plan(allow_unknown_capacity='yes')
        (self.folder / 'campaign.xml').write_text('<CampaignEngine>')
        self.assertFalse(self.plan().ready_for_copy)

    def test_cargo_and_credit_references(self):
        path = self.folder / 'campaign.xml'
        text = path.read_text(encoding='utf-8')
        begin = text.index('<cargo z="4"')
        end = text.index('</cargo>', begin) + len('</cargo>')
        cargo = text[begin:end]
        text = text[:begin] + '<cargo ref="4"/>' + text[end:]
        text = text.replace('</objects>', cargo + '</objects>')
        text = text.replace('<c z="7"><value>120.0</value></c>', '<c ref="7"/>')
        text = text.replace('</objects>', '<neutralValue z="7"><value>120.0</value></neutralValue></objects>')
        path.write_text(text, encoding='utf-8')
        self.assertEqual({r.target: r.value for r in self.snapshot().resources}['credits'], '120.0')

    def test_cyclic_and_duplicate_object_references_refused(self):
        path = self.folder / 'campaign.xml'
        base = path.read_text(encoding='utf-8')
        for addition in ('<object z="2"/>', '<object z="11" ref="11"/>'):
            text = base.replace('</objects>', addition + '</objects>')
            if '11' in addition:
                text = text.replace('<playerFleet ref="2"/>', '<playerFleet ref="11"/>')
            path.write_text(text, encoding='utf-8')
            self.assertNotIn('credits', {r.target for r in self.snapshot().resources})

    def test_duplicate_stack_and_unknown_nested_identifier_refused(self):
        path = self.folder / 'campaign.xml'
        base = path.read_text(encoding='utf-8')
        stack = '<CIStack t="RESOURCES" s="2.0"><d cl="st">supplies</d></CIStack>'
        for text in (base.replace('</s>', stack+'</s>'), base.replace('>supplies</d>', '>sup<unknown/>plies</d>')):
            path.write_text(text, encoding='utf-8')
            self.assertNotIn('commodity:supplies', {r.target for r in self.snapshot().resources})

    def test_nonempty_partials_refuse_commodity_changes(self):
        path = self.folder / 'campaign.xml'
        path.write_text(path.read_text(encoding='utf-8').replace('<partials></partials>', '<partials><entry><string>supplies</string><float>0.5</float></entry></partials>'), encoding='utf-8')
        self.assertEqual(self.plan('commodity:supplies', 10, allow_unknown_capacity=True).changes[0].outcome, 'REFUSED')

    def test_attribute_lexing_does_not_select_numeric_text_inside_other_attribute(self):
        path = self.folder / 'campaign.xml'
        path.write_text(path.read_text(encoding='utf-8').replace('stats sp="2"', 'stats unknown=\' sp="999"\' sp="2"'), encoding='utf-8')
        self.assertEqual({r.target: r.value for r in self.snapshot().resources}['story_points'], '2')

    def test_source_hash_change_refused(self):
        inspection = inspect_save(self.folder)
        path = self.folder / 'campaign.xml'
        path.write_text(path.read_text(encoding='utf-8').replace('120.0', '121.0'), encoding='utf-8')
        snapshot = locate_resources(self.folder, inspection)
        self.assertEqual(snapshot.status, 'SOURCE_CHANGED')
        self.assertFalse(snapshot.resources)

    def test_unbounded_numeric_encoding_refused(self):
        path = self.folder / 'campaign.xml'
        path.write_text(path.read_text(encoding='utf-8').replace('sp="2"', 'sp="1e1000000000"'), encoding='utf-8')
        self.assertNotIn('story_points', {r.target for r in self.snapshot().resources})

    def test_catalog_detects_source_replacement(self):
        root = self.root / 'source'
        path = root / 'data/campaign/commodities.csv'
        path.parent.mkdir(parents=True)
        path.write_text('id,name\nneutral_ore,Neutral\n')
        real_open = Path.open
        def replacing_open(selected, *args, **kwargs):
            if selected == path and args == ('rb',):
                selected.write_text('id,name\nchanged_id,Neutral\n')
            return real_open(selected, *args, **kwargs)
        with patch.object(Path, 'open', replacing_open):
            self.assertEqual(read_commodity_catalog((root,)).status, 'UNAVAILABLE')

    def test_catalog_from_synthetic_source_and_malformed_header(self):
        root = self.root / 'source'
        path = root / 'data/campaign/commodities.csv'
        path.parent.mkdir(parents=True)
        path.write_text('id,name\nneutral_ore,Neutral commodity\n', encoding='utf-8')
        before = path.read_bytes()
        catalog = read_commodity_catalog((root,))
        self.assertEqual(catalog.status, 'PARSED')
        self.assertEqual(catalog.identifiers, frozenset({'neutral_ore'}))
        self.assertEqual(path.read_bytes(), before)
        path.write_text('name\nunknown\n')
        self.assertEqual(read_commodity_catalog((root,)).status, 'UNAVAILABLE')

    def test_native_catalog_excludes_disabled_and_unknown_mods(self):
        from starsector_variant_generator.core.models import ModInfo
        roots = []
        for name in ('core', 'enabled', 'disabled', 'unknown'):
            root = self.root / name
            csv_file = root / 'data/campaign/commodities.csv'
            csv_file.parent.mkdir(parents=True)
            csv_file.write_text(f'id,name\n{name}_commodity,Neutral\n')
            roots.append(root)
        sources = [ModInfo(name, name, None, root, flag) for name, root, flag in zip(('core','enabled','disabled','unknown'), roots, (True, True, False, None), strict=False)]
        with patch('starsector_variant_generator.core.scanner.Scanner.discover_sources', return_value=sources):
            catalog = api.run_save_commodity_catalog(self.root)
        self.assertEqual(catalog.identifiers, frozenset({'core_commodity', 'enabled_commodity'}))

    def test_cli_plan_and_resource_inspection_are_stdout_only(self):
        from starsector_variant_generator.cli.main import main
        before = source_hashes(self.folder)
        for argv in (['save','plan',str(self.folder),'--set','credits=200'], ['save','inspect',str(self.folder),'--resources']):
            output = io.StringIO()
            with patch('sys.argv', ['voidsmith', *argv]), redirect_stdout(output):
                self.assertEqual(main(), 0)
            self.assertIn('source_hashes', json.loads(output.getvalue()))
        self.assertEqual(source_hashes(self.folder), before)


if __name__ == '__main__':
    unittest.main()

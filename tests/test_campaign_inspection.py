from __future__ import annotations

import hashlib
import io
import json
import subprocess
import unittest
from contextlib import redirect_stdout
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from starsector_variant_generator.campaign import format as save_format
from starsector_variant_generator.campaign.models import FactStatus


def make_save(path, extra="", version="0.98a-RC8", save_version="0.6", compressed="false"):
    path.mkdir()
    (path / "descriptor.xml").write_text(
        f'<SaveGameData><characterName>Synthetic Pilot</characterName>'
        f'<gameVersion>{version}</gameVersion><saveFileVersion>{save_version}</saveFileVersion>'
        f'<compressed>{compressed}</compressed>{extra}</SaveGameData>', encoding="utf-8")
    (path / "campaign.xml").write_text('<CampaignEngine><unknown ref="42"/></CampaignEngine>', encoding="utf-8")
    return path


def hashes(path):
    return {p.name: hashlib.sha256(p.read_bytes()).hexdigest() for p in path.iterdir()}


class CampaignInspectionTests(unittest.TestCase):
    def setUp(self):
        temp = TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        self.root = Path(temp.name)

    def test_inspection_facts_hashes_and_nonmutation(self):
        folder = make_save(self.root / "save")
        before = hashes(folder)
        result = save_format.inspect_save(folder)
        self.assertEqual(result.status, "READABLE")
        self.assertEqual(dict(result.source_hashes), before)
        self.assertEqual(hashes(folder), before)
        facts = {f.name: f for f in result.facts}
        self.assertEqual(facts["characterName"].value, "Synthetic Pilot")
        self.assertEqual(facts["credits"].status, FactStatus.UNAVAILABLE)
        self.assertIsNone(facts["credits"].value)
        self.assertEqual(facts["capacity_overage_effects"].status, FactStatus.UNKNOWN)
        self.assertEqual(json.loads(json.dumps(result.to_payload()))["schema_version"], "campaign-inspection-v1")

    def test_version_and_compression_boundaries(self):
        cases = [("0.99a-RC1", "0.6", "false", "UNSUPPORTED_VERSION"),
                 ("0.97a", "0.6", "false", "UNSUPPORTED_VERSION"),
                 ("0.98a-RC8", "0.7", "false", "UNSUPPORTED_VERSION"),
                 ("0.98a-RC8", "0.6", "true", "UNSUPPORTED_FORMAT")]
        for index, (version, save_version, compressed, status) in enumerate(cases):
            with self.subTest(version=version, save_version=save_version, compressed=compressed):
                folder = make_save(self.root / str(index), version=version, save_version=save_version, compressed=compressed)
                before = hashes(folder)
                self.assertEqual(save_format.inspect_save(folder).status, status)
                self.assertEqual(hashes(folder), before)

    def test_bad_campaign_is_refused_without_mutation(self):
        cases = [('<CampaignEngine>', 'MALFORMED'), ('<foreign/>', 'NOT_A_SAVE'),
                 ('<!DOCTYPE CampaignEngine><CampaignEngine/>', 'UNSAFE_XML'),
                 ('<!DOCTYPE CampaignEngine [<!ENTITY x "value">]><CampaignEngine>&x;</CampaignEngine>', 'UNSAFE_XML'),
                 ('<!DOCTYPE CampaignEngine SYSTEM "file:///private"><CampaignEngine/>', 'UNSAFE_XML')]
        for index, (content, status) in enumerate(cases):
            with self.subTest(content=content):
                folder = make_save(self.root / str(index))
                (folder / "campaign.xml").write_text(content)
                before = hashes(folder)
                result = save_format.inspect_save(folder)
                self.assertEqual(result.status, status)
                self.assertFalse(result.facts)
                self.assertEqual(hashes(folder), before)

    def test_descriptor_duplicate_and_nested_scalar_refused(self):
        for index, extra in enumerate(('<gameVersion>0.98a-RC8</gameVersion>', '<characterName><nested/></characterName>')):
            folder = make_save(self.root / str(index), extra=extra)
            self.assertEqual(save_format.inspect_save(folder).status, "MALFORMED")

    def test_unknown_fields_remain_uninterpreted(self):
        folder = make_save(self.root / "save", extra='<future><credits>999</credits></future>')
        result = save_format.inspect_save(folder)
        self.assertEqual(result.status, "READABLE")
        self.assertIsNone(next(f for f in result.facts if f.name == "credits").value)

    def test_size_depth_and_element_limits(self):
        folder = make_save(self.root / "save")
        with patch.object(save_format, "MAX_CAMPAIGN_BYTES", 1):
            self.assertEqual(save_format.inspect_save(folder).status, "LIMIT_EXCEEDED")
        (folder / "campaign.xml").write_text('<CampaignEngine><x><y/></x></CampaignEngine>')
        with patch.object(save_format, "MAX_DEPTH", 2):
            self.assertEqual(save_format.inspect_save(folder).status, "LIMIT_EXCEEDED")
        with patch.object(save_format, "MAX_ELEMENTS", 2):
            self.assertEqual(save_format.inspect_save(folder).status, "LIMIT_EXCEEDED")

    def test_utf16_refused(self):
        folder = make_save(self.root / "save")
        (folder / "campaign.xml").write_text('<CampaignEngine/>', encoding="utf-16")
        self.assertEqual(save_format.inspect_save(folder).status, "UNSUPPORTED_FORMAT")

    def test_non_utf8_declaration_refused(self):
        folder = make_save(self.root / "save")
        (folder / "campaign.xml").write_text('<?xml version="1.0" encoding="ISO-8859-1"?><CampaignEngine/>')
        self.assertEqual(save_format.inspect_save(folder).status, "UNSUPPORTED_FORMAT")

    def test_descriptor_limits_and_doctype_refusal(self):
        folder = make_save(self.root / "save")
        with patch.object(save_format, "MAX_DESCRIPTOR_BYTES", 1):
            self.assertEqual(save_format.inspect_save(folder).status, "LIMIT_EXCEEDED")
        (folder / "descriptor.xml").write_text('<!DOCTYPE SaveGameData><SaveGameData/>')
        self.assertEqual(save_format.inspect_save(folder).status, "UNSAFE_XML")

    @unittest.skipUnless(__import__('os').name == 'nt', 'Windows junction test')
    def test_windows_junction_refused(self):
        folder = make_save(self.root / "save")
        link = self.root / "junction"
        result = subprocess.run(['cmd', '/c', 'mklink', '/J', str(link), str(folder)], capture_output=True)
        if result.returncode:
            self.skipTest('Host does not permit creating junctions')
        self.assertEqual(save_format.inspect_save(link).status, "UNSAFE_PATH")

    def test_descriptor_changes_during_campaign_read(self):
        folder = make_save(self.root / "save")
        real_read = save_format._read_xml
        def changing_read(path, *args):
            result = real_read(path, *args)
            if path.name == "campaign.xml":
                (folder / "descriptor.xml").write_text('<changed/>')
            return result
        with patch.object(save_format, "_read_xml", changing_read):
            self.assertEqual(save_format.inspect_save(folder).status, "SOURCE_CHANGED")

    def test_parent_traversal_refused(self):
        folder = make_save(self.root / "save")
        self.assertEqual(save_format.inspect_save(folder / ".." / "save").status, "UNSAFE_PATH")

    def test_invalid_path_refused(self):
        self.assertEqual(save_format.inspect_save(Path('invalid\x00path')).status, "UNSAFE_PATH")

    def test_campaign_modules_do_not_import_fitting_engines(self):
        import ast
        blocked = {'generation', 'scoring', 'profiles', 'validation', 'analysis'}
        for module in Path(save_format.__file__).parent.glob('*.py'):
            tree = ast.parse(module.read_text(encoding='utf-8'))
            for node in ast.walk(tree):
                if isinstance(node, ast.ImportFrom):
                    self.assertFalse(blocked.intersection((node.module or '').split('.')), module.name)
                elif isinstance(node, ast.Import):
                    for alias in node.names:
                        self.assertFalse(blocked.intersection(alias.name.split('.')), module.name)

    def test_links_refused(self):
        folder = make_save(self.root / "save")
        link = self.root / "link"
        try:
            link.symlink_to(folder, target_is_directory=True)
        except OSError:
            self.skipTest("Host does not permit creating symlinks")
        self.assertEqual(save_format.inspect_save(link).status, "UNSAFE_PATH")
        link.unlink()
        link.symlink_to(self.root, target_is_directory=True)
        self.assertEqual(save_format.inspect_save(link / "save").status, "UNSAFE_PATH")
        original = folder / "campaign.xml"
        original.rename(folder / "other.xml")
        original.symlink_to(folder / "other.xml")
        self.assertEqual(save_format.inspect_save(folder).status, "UNSAFE_PATH")

    def test_source_replacement_detected(self):
        folder = make_save(self.root / "save")
        real_open = Path.open
        def replacing_open(path, *args, **kwargs):
            if path.name == "campaign.xml" and args == ("rb",):
                path.write_text('<CampaignEngine><changed/></CampaignEngine>')
            return real_open(path, *args, **kwargs)
        with patch.object(Path, "open", replacing_open):
            self.assertEqual(save_format.inspect_save(folder).status, "SOURCE_CHANGED")

    def test_missing_files(self):
        self.assertEqual(save_format.inspect_save(self.root).status, "NOT_A_SAVE")

    def test_api_and_cli_inspect(self):
        from starsector_variant_generator import api
        from starsector_variant_generator.cli.main import main
        folder = make_save(self.root / "save")
        self.assertEqual(api.run_save_inspect(folder).status, "READABLE")
        for content, status, exit_code in [('<CampaignEngine/>', 'READABLE', 0), ('<CampaignEngine>', 'MALFORMED', 1)]:
            (folder / "campaign.xml").write_text(content)
            output = io.StringIO()
            with patch('sys.argv', ["voidsmith", "save", "inspect", str(folder)]), redirect_stdout(output):
                self.assertEqual(main(), exit_code)
            self.assertEqual(json.loads(output.getvalue())["status"], status)


if __name__ == '__main__':
    unittest.main()

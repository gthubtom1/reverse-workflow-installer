"""Windows Craft target-path preflight only; no real installs or native/provider calls."""
import copy
import os
from pathlib import Path
from types import SimpleNamespace
import unittest
from unittest.mock import patch

import test_craft as fixtures
import workflow as w
from configuration import atomic, encode_json, load_json
from versions import InstallError

LONG_FILE = 'licenses/cargo/winapi-x86_64-pc-windows-gnu-0.4.0/retep998--winapi-rs--796a8e6c2971--LICENSE-MIT'


def platform(name):
    class Proxy:
        def __getattr__(self, key):
            return name if key == 'name' else getattr(os, key)
    return patch.object(w, 'os', Proxy())


def inputs(root, files=None):
    selected = {'components':['reverse','spec_kit','craft'], 'root':str(root)}
    components = {'craft':{'files':{name:'0'*64 for name in (files or [LONG_FILE])}}}
    resources = {'files':{'skills/reconstruction-execution/SKILL.md':'0'*64}}
    return selected, components, resources


class CraftPathLimits(unittest.TestCase):
    def setUp(self):
        self.repo = fixtures.REPO

    def test_actual_final_bundle_license_relative_and_short_root(self):
        # Exact relative path observed in the final bundle's actual license inventory.
        with platform('nt'):
            w._craft_target_path_preflight(*inputs(Path('D:/w')))
            prefix = 'D:/' + 'x'*120
            target = Path(prefix) / 'versions' / ('0'*20) / 'craft-bundle' / LONG_FILE
            count = len(str(target).encode('utf-16-le'))//2
            # Recreate the reported 268-unit destination; preflight also reserves retries.
            root = Path('D:/' + 'x'*(120+268-count))
            with self.assertRaisesRegex(InstallError,'craft-path-too-long.*选择更短安装根') as error:
                w._craft_target_path_preflight(*inputs(root))
            self.assertIn('file=277/259',str(error.exception))

    def test_utf16_emoji_boundary_and_atomic_temp_budget(self):
        # Deepest parent holds a short file so the temp basename budget dominates.
        parent_units = 259-1-24
        relative = 'd'*80 + '/x'
        root_units = parent_units - len('/versions/' + '0'*20 + '-00000000/craft-bundle/' + 'd'*80)
        root = 'D:/' + 'a'*(root_units-3)
        with platform('nt'):
            w._craft_target_path_preflight(*inputs(Path(root),[relative]))
            # One emoji has two UTF16 units, despite Python len==1.
            with self.assertRaisesRegex(InstallError,'atomic-temp=260/259'):
                w._craft_target_path_preflight(*inputs(Path(root[:-1]+'😀'),[relative]))

    def test_adapter_resource_mapping_is_also_checked(self):
        selected, components, resources = inputs(Path('D:/w'),['entry.py'])
        resources['files']['deep/'+'x'*240+'.md']='0'*64
        with platform('nt'), self.assertRaisesRegex(InstallError,'craft-pi/deep/'):
            w._craft_target_path_preflight(selected,components,resources)

    def test_noncraft_and_nonwindows_are_unaffected(self):
        selected, components, resources=inputs(Path('D:/'+'x'*300))
        with platform('posix'):
            w._craft_target_path_preflight(selected,components,resources)
        selected['components']=['reverse','spec_kit']
        with platform('nt'):
            w._craft_target_path_preflight(selected,{}, {})

    def test_plan_and_apply_reject_before_commands_lock_journal_or_any_root_write(self):
        case=fixtures.CraftTests(methodName='test_default_all_does_not_enable_craft')
        case.setUp()
        try:
            atomic(case.bundle / LONG_FILE,b'license fixture bytes')
            manifest=load_json(case.bundle/'craft-bundle.json')
            import craft
            manifest['files'][LONG_FILE]=craft.inventory(case.bundle)[LONG_FILE]
            atomic(case.bundle/'craft-bundle.json',encode_json(manifest))
            with platform('nt'):
                plan=case.plan()
            long_root=case.base / ('x'*140)
            case.args.root=str(long_root)
            case.calls.clear()
            with platform('nt'), patch.object(w,'run',side_effect=AssertionError('must not run')),self.assertRaisesRegex(InstallError,'craft-path-too-long'):
                case.plan()
            self.assertFalse(long_root.exists())
            self.assertEqual(case.calls,[])
            plan['scope']['root']=str(long_root)
            with platform('nt'),patch.object(w,'Journal',side_effect=AssertionError('no journal')),patch.object(w,'locked',side_effect=AssertionError('no lock')),patch.object(w,'run',side_effect=AssertionError('no command')),self.assertRaisesRegex(InstallError,'craft-path-too-long'):
                w.install(plan,case.args)
            self.assertFalse((long_root/'.installer').exists())
            self.assertFalse(case.root.exists())
        finally:
            case.tearDown()


if __name__=='__main__': unittest.main()

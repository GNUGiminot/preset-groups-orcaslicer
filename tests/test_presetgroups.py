"""Unit tests for Preset Groups that need no running OrcaSlicer.

Run with: python -m unittest discover -s tests
"""

import importlib.util
import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import types
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)


class FakePreset:
    def __init__(self, name, values, user=True, alias="", compatible=True, dirty=False, visible=True):
        self.name, self.alias, self.is_compatible, self.is_dirty = name, alias, compatible, dirty
        self.is_visible, self.is_default = visible, False
        self._values, self._user = values, user

    def is_user(self):
        return self._user

    def config_keys(self):
        return list(self._values)

    def config_value(self, key):
        return self._values.get(key)


class FakeCollection:
    def __init__(self, presets, edited=None):
        self.presets = presets
        self.edited = edited or (presets[0] if presets else None)

    def size(self):
        return len(self.presets)

    def preset(self, index):
        return self.presets[index]

    def find_preset(self, name):
        return next((p for p in self.presets if p.name == name), None)

    def get_edited_preset(self):
        return self.edited


class FakeBundle:
    def __init__(self, filaments, printers, prints, slots, colours="#FF0000;#00FF00"):
        self.filaments, self.printers, self.prints = filaments, printers, prints
        self._slots, self._colours = slots, colours

    def current_printer_preset(self):
        return self.printers.edited

    def current_process_preset(self):
        return self.prints.edited

    def current_filament_preset_names(self):
        return self._slots

    def full_config_value(self, key):
        return self._colours if key == "filament_colour" else None


def load_plugin():
    orca = types.ModuleType("orca")
    orca.pages = types.SimpleNamespace(PagesPluginCapabilityBase=object)
    orca.base = object
    orca.plugin = lambda cls: cls
    orca.register_capability = lambda cls: None
    orca.host = types.SimpleNamespace(app_info=lambda: {"language": "en"})
    sys.modules["orca"] = orca
    spec = importlib.util.spec_from_file_location("presetgroups", os.path.join(ROOT, "presetgroups.py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module, orca


pg, fake_orca = load_plugin()

PLA_BASE = {"filament_type": "PLA", "filament_vendor": "Generic", "nozzle_temperature": "220;220",
            "hot_plate_temp": "60;60", "compatible_printers": '"Qidi Q1 Pro 0.4 nozzle"', "filament_colour": "#FFFFFF",
            "filament_flow_ratio": "0.98", "pressure_advance": "0.04"}


def filament(name, **changes):
    values = dict(PLA_BASE, inherits="Qidi Generic PLA @Qidi Q1 Pro 0.4 nozzle", compatible_printers="")
    values.update({k: str(v) for k, v in changes.items()})
    return FakePreset(name, values)


def sample_bundle(**kwargs):
    system = FakePreset("Qidi Generic PLA @Qidi Q1 Pro 0.4 nozzle", dict(PLA_BASE), user=False)
    presets = [
        system,
        filament("Eryone PLA black", filament_vendor="Eryone", filament_colour="#111111", nozzle_temperature="215;215"),
        filament("Eryone PLA black copy", filament_vendor="eryone ", filament_colour="#111111", nozzle_temperature="215;215"),
        filament("(#29) PLA Black - Eryone - PipSpool", filament_vendor="ERYONE", filament_colour="#111111",
                 nozzle_temperature="230;230", hot_plate_temp="65;65", filament_flow_ratio="0.95", pressure_advance="0.02",
                 filament_max_volumetric_speed="12"),
        filament("Чёрный PLA Element", filament_vendor="Element", filament_colour="#222222", filament_flow_ratio="0.9"),
    ]
    printer = FakePreset("Qidi Q1 Pro 0.4 nozzle - Мастерская", {"inherits": "Qidi Q1 Pro 0.4 nozzle", "printer_model": "Qidi Q1 Pro",
                         "nozzle_diameter": "0.4", "printable_area": "0x0,245x0,245x245,0x245", "printable_height": "240"})
    system_printer = FakePreset("Qidi Q1 Pro 0.4 nozzle", {"printer_model": "Qidi Q1 Pro"}, user=False)
    process = FakePreset("0.20mm Standard @Qidi Q1 Pro_general", {"inherits": "0.20mm Standard @Qidi Q1 Pro", "layer_height": "0.2",
                         "wall_loops": "3", "sparse_infill_density": "15%"})
    system_process = FakePreset("0.20mm Standard @Qidi Q1 Pro", {"layer_height": "0.2"}, user=False)
    return FakeBundle(FakeCollection(presets, kwargs.get("edited_filament", presets[1])), FakeCollection([printer, system_printer]),
                      FakeCollection([process, system_process]), kwargs.get("slots", ["Eryone PLA black", "Чёрный PLA Element"]))


class SplitValues(unittest.TestCase):
    def test_mixed_quoting_as_orca_writes_it(self):
        self.assertEqual(pg.split_values('PLA;"Qidi Q1 Pro 0.4 nozzle";""'), ["PLA", "Qidi Q1 Pro 0.4 nozzle", ""])

    def test_escapes_inside_quotes(self):
        self.assertEqual(pg.split_values(r'"a \"b\"";"x\ny"'), ['a "b"', "x\ny"])

    def test_numbers_and_empty(self):
        self.assertEqual(pg.split_values("220;225"), ["220", "225"])
        self.assertEqual(pg.split_values(""), [])
        self.assertEqual(pg.split_values(None), [])


class Facts(unittest.TestCase):
    def test_filament_facts_take_the_first_extruder(self):
        facts = pg.facts_of("filament", {"filament_type": "PETG", "nozzle_temperature": "240;245", "hot_plate_temp": "0",
                                         "textured_plate_temp": "75", "filament_colour": "#1A2B3C"})
        self.assertEqual((facts["type"], facts["nozzle"], facts["bed"], facts["color"]), ("PETG", "240", "75", "#1A2B3C"))

    def test_bad_colour_is_dropped(self):
        self.assertEqual(pg.facts_of("filament", {"filament_colour": "red"})["color"], "")

    def test_bed_size(self):
        self.assertEqual(pg.bed_size("0x0,245x0,245x245,0x245"), "245×245")
        self.assertEqual(pg.bed_size("nonsense"), "")


class Sources(unittest.TestCase):
    def test_pipspool_names(self):
        self.assertEqual(pg.source_of("(#10) PETG Белый - FDplast - PipSpool"), "pipspool")
        self.assertEqual(pg.source_of("PETG Black FDPlast 0.4 nozzle"), "own")

    def test_vendor_spellings_share_a_key(self):
        self.assertEqual(len({pg.vendor_key(v) for v in ("FDPlast  ", "fdplast", "FDplast", "FD-plast")}), 1)


class ReadPresets(unittest.TestCase):
    def setUp(self):
        self.data = pg.read_presets(sample_bundle())

    def test_only_user_presets(self):
        names = [r["name"] for r in self.data["kinds"]["filament"]]
        self.assertNotIn("Qidi Generic PLA @Qidi Q1 Pro 0.4 nozzle", names)
        self.assertEqual(len(names), 4)
        self.assertEqual([r["name"] for r in self.data["kinds"]["printer"]], ["Qidi Q1 Pro 0.4 nozzle - Мастерская"])

    def test_printers_come_from_the_parent_when_the_preset_has_none(self):
        record = self.data["kinds"]["filament"][0]
        self.assertEqual(record["printers"], ["Qidi Q1 Pro 0.4 nozzle"])
        self.assertEqual(self.data["printers"], ["Qidi Q1 Pro 0.4 nozzle"])

    def test_slots_and_active_presets(self):
        by_name = {r["name"]: r for r in self.data["kinds"]["filament"]}
        self.assertEqual(by_name["Eryone PLA black"]["selected"], [1])
        self.assertEqual(by_name["Чёрный PLA Element"]["selected"], [2])
        self.assertEqual([s["color"] for s in self.data["slots"]], ["#FF0000", "#00FF00"])
        self.assertEqual(self.data["kinds"]["process"][0]["selected"], [1])

    def test_changes_from_the_parent(self):
        by_name = {r["name"]: r for r in self.data["kinds"]["filament"]}
        keys = {c["key"] for c in by_name["Чёрный PLA Element"]["changes"]}
        self.assertEqual(keys, {"filament_vendor", "filament_colour", "filament_flow_ratio"})

    def test_duplicates(self):
        clusters = {c["reason"]: c for c in self.data["duplicates"]["filament"]}
        # Same settings apart from the vendor's spelling: one setting differs.
        near = clusters["near"]
        self.assertIn("Eryone PLA black", near["names"])
        self.assertIn("Eryone PLA black copy", near["names"])
        self.assertIn("filament_vendor", near["values"])
        # The PipSpool preset differs in many settings but has the same vendor, type and colour.
        self.assertIn("(#29) PLA Black - Eryone - PipSpool", near["names"])
        self.assertNotIn("Чёрный PLA Element", near["names"])

    def test_other_colour_is_another_spool(self):
        bundle = sample_bundle()
        bundle.filaments.presets.append(filament("Eryone PLA white", filament_vendor="Eryone", filament_colour="#FAFAFA",
                                                 nozzle_temperature="215;215"))
        names = {n for c in pg.read_presets(bundle)["duplicates"]["filament"] for n in c["names"]}
        self.assertNotIn("Eryone PLA white", names)

    def test_identical_settings(self):
        bundle = sample_bundle()
        twin = filament("Eryone PLA black (2)", filament_vendor="Eryone", filament_colour="#111111", nozzle_temperature="215;215")
        bundle.filaments.presets.append(twin)
        clusters = pg.read_presets(bundle)["duplicates"]["filament"]
        # The twin joins the cluster its original is in, so one preset never shows up twice.
        self.assertEqual(len([c for c in clusters if "Eryone PLA black" in c["names"]]), 1)
        self.assertIn("Eryone PLA black (2)", clusters[0]["names"])
        bundle.filaments.presets = [p for p in bundle.filaments.presets if p.name in ("Eryone PLA black", "Eryone PLA black (2)")]
        clusters = pg.read_presets(bundle)["duplicates"]["filament"]
        self.assertEqual([(c["reason"], c["names"]) for c in clusters], [("same", ["Eryone PLA black", "Eryone PLA black (2)"])])

    def test_dismissed_cluster_is_left_out(self):
        cluster = self.data["duplicates"]["filament"][0]
        data = pg.read_presets(sample_bundle(), {"filament": ["\n".join(cluster["names"])]})
        self.assertEqual(data["duplicates"]["filament"], [])

    def test_healthy_presets_have_no_issues(self):
        for kind in pg.KINDS:
            for record in self.data["kinds"][kind]:
                with self.subTest(name=record["name"]):
                    self.assertEqual(record["issues"], [])

    def test_missing_base_preset(self):
        bundle = sample_bundle()
        bundle.filaments.presets.append(filament("Old PLA", inherits="Gone Generic PLA", compatible_printers='"Qidi Q1 Pro 0.4 nozzle"'))
        record = next(r for r in pg.read_presets(bundle)["kinds"]["filament"] if r["name"] == "Old PLA")
        self.assertEqual(record["issues"], ["orphan"])

    def test_printer_that_is_gone(self):
        bundle = sample_bundle()
        bundle.filaments.presets.append(filament("Ender PLA", compatible_printers='"Creality Ender-3 0.4 nozzle"'))
        # A system printer the user did not pick counts as gone too.
        bundle.printers.presets.append(FakePreset("Creality Ender-3 0.4 nozzle", {}, user=False, visible=False))
        record = next(r for r in pg.read_presets(bundle)["kinds"]["filament"] if r["name"] == "Ender PLA")
        self.assertEqual(record["issues"], ["no_printer"])
        self.assertEqual(record["printers"], ["Creality Ender-3 0.4 nozzle"])

    def test_renamed_base_preset(self):
        bundle = sample_bundle()
        system = bundle.filaments.presets[0]
        renamed = FakeCollection(bundle.filaments.presets, bundle.filaments.edited)
        # Orca finds a preset under the name it had before a rename.
        renamed.find_preset = lambda name: system if name in (system.name, "Old Qidi PLA") else None
        bundle.filaments = renamed
        bundle.filaments.presets.append(filament("Kept PLA", inherits="Old Qidi PLA"))
        record = next(r for r in pg.read_presets(bundle)["kinds"]["filament"] if r["name"] == "Kept PLA")
        self.assertEqual((record["issues"], record["parent_now"]), ([], system.name))


class Compare(unittest.TestCase):
    def test_only_differences_base_first(self):
        result = pg.compare_presets(["a", "b"], {
            "a": {"inherits": "X", "nozzle_temperature": "220", "name": "a", "filament_type": "PLA"},
            "b": {"inherits": "Y", "nozzle_temperature": "230", "name": "b", "filament_type": "PLA", "extra": "1"}})
        self.assertEqual([r["key"] for r in result["rows"]], ["inherits", "extra", "nozzle_temperature"])
        self.assertEqual(result["rows"][1]["values"], ["", "1"])
        self.assertEqual((result["same"], result["truncated"]), (1, False))

    def test_compare_reads_presets(self):
        result = pg.compare(sample_bundle(), "filament", ["Eryone PLA black", "Чёрный PLA Element"])
        self.assertIn("filament_flow_ratio", [r["key"] for r in result["rows"]])
        with self.assertRaises(ValueError):
            pg.compare(sample_bundle(), "filament", ["Eryone PLA black", "nope"])


class Config(unittest.TestCase):
    def test_groups_are_cleaned(self):
        config = pg.clean_config({"groups": {"filament": [
            {"id": "a", "name": "  PETG   daily ", "color": "#0ea5e9", "items": ["x", "y"]},
            {"id": "a", "name": "Second", "color": "javascript:", "items": ["y", "z", 5]},
            {"id": "c", "name": "   ", "items": []},
            "junk"]}, "language": "de"})
        groups = config["groups"]["filament"]
        self.assertEqual([g["name"] for g in groups], ["PETG daily", "Second"])
        self.assertNotEqual(groups[1]["id"], "a")
        self.assertIn(groups[1]["color"], pg.GROUP_COLORS)
        self.assertEqual(groups[1]["items"], ["z", "5"])
        self.assertEqual(config["groups"]["printer"], [])
        self.assertEqual(config["language"], "auto")

    def test_rules_notes_and_the_rest(self):
        config = pg.clean_config({
            "groups": {"filament": [{"id": "g1", "name": "PETG", "items": [], "excluded": ["x", "x", 3],
                                     "rule": {"type": "  PETG,  PLA ", "vendor": "", "junk": "1", "text": "a" * 100}}]},
            "notes": {"filament": {"x": "  dry 4 h  ", "y": "   ", "z": "n" * 900}, "printer": "bad"},
            "favorites": {"process": ["p", "p"]}, "seen_ready": 1, "theme": "neon", "favorites_first": False})
        group = config["groups"]["filament"][0]
        self.assertEqual(group["rule"], {"type": "PETG, PLA", "text": "a" * pg.MAX_RULE})
        self.assertEqual(group["excluded"], ["x", "3"])
        self.assertEqual(config["notes"]["filament"], {"x": "dry 4 h", "z": "n" * pg.MAX_NOTE})
        self.assertEqual(config["notes"]["printer"], {})
        self.assertEqual(config["favorites"]["process"], ["p"])
        self.assertEqual((config["seen_ready"], config["theme"], config["favorites_first"]), (True, "auto", False))

    def test_defaults_are_clean(self):
        self.assertEqual(pg.clean_config({}), pg.clean_config(pg.DEFAULT_CONFIG))
        self.assertEqual(pg.clean_config(pg.DEFAULT_CONFIG), pg.DEFAULT_CONFIG)

    def test_cyrillic_names_survive(self):
        config = pg.clean_config({"groups": {"process": [{"id": "g1", "name": "Гараж под каретки", "items": ["0.20mm Мастерская"]}]}})
        self.assertEqual(config["groups"]["process"][0]["name"], "Гараж под каретки")
        self.assertEqual(json.loads(json.dumps(config, ensure_ascii=False))["groups"]["process"][0]["items"], ["0.20mm Мастерская"])


class Apply(unittest.TestCase):
    def setUp(self):
        self.calls = []
        editor = types.SimpleNamespace(begin_update=lambda *a, **k: self.calls.append((a, k)))
        fake_orca.host.preset = types.SimpleNamespace(filament=editor, printer=editor, process=editor)

    def test_filament_goes_to_the_slot(self):
        fake_orca.host.preset_bundle = lambda: sample_bundle()
        pg.apply_preset("filament", "Чёрный PLA Element", 2)
        self.assertEqual(self.calls, [((2, "Чёрный PLA Element"), {})])

    def test_unsaved_changes_stop_the_switch(self):
        bundle = sample_bundle()
        bundle.filaments.edited.is_dirty = True
        fake_orca.host.preset_bundle = lambda: bundle
        with self.assertRaises(ValueError):
            pg.apply_preset("filament", "Чёрный PLA Element", 2)
        self.assertEqual(self.calls, [])

    def test_unknown_preset(self):
        fake_orca.host.preset_bundle = lambda: sample_bundle()
        with self.assertRaises(ValueError):
            pg.apply_preset("process", "nope")

    def test_slot_out_of_range(self):
        fake_orca.host.preset_bundle = lambda: sample_bundle()
        with self.assertRaises(ValueError):
            pg.apply_preset("filament", "Чёрный PLA Element", 3)
        self.assertEqual(self.calls, [])

    def test_several_slots_in_order(self):
        fake_orca.host.preset_bundle = lambda: sample_bundle()
        done = pg.apply_slots([{"slot": 2, "name": "Eryone PLA black"}, {"slot": 1, "name": "Чёрный PLA Element"}])
        self.assertEqual(done, 2)
        self.assertEqual(self.calls, [((1, "Чёрный PLA Element"), {}), ((2, "Eryone PLA black"), {})])


class PageLogic(unittest.TestCase):
    """The part of the page between PURE:BEGIN and PURE:END, run in Node."""

    HARNESS = r"""
const P=(name,facts,extra={})=>({name,label:name,kind:"filament",parent:"",printers:["Qidi Q1 Pro 0.4 nozzle"],facts,...extra});
const list=[P("PETG black",{type:"PETG",vendor:"FDplast"}),P("PETG white",{type:"PETG",vendor:"FDPlast  "}),
  P("PLA red",{type:"PLA",vendor:"Eryone"}),P("TPU",{type:"TPU",vendor:"Eryone"},{printers:[]})];
const out={};
out.type=ruleMatches({type:"petg"},list[0]);
out.vendor=list.filter(p=>ruleMatches({vendor:"fd-plast"},p)).map(p=>p.name);
out.anyOf=list.filter(p=>ruleMatches({type:"PLA, TPU"},p)).map(p=>p.name);
out.both=list.filter(p=>ruleMatches({type:"PETG",text:"white"},p)).map(p=>p.name);
out.printer=list.filter(p=>ruleMatches({printer:"q1 pro"},p)).map(p=>p.name);
out.empty=ruleMatches({},list[0]);
const groups=[{id:"a",items:["PLA red"],rule:{},excluded:[]},{id:"b",items:[],rule:{type:"PETG"},excluded:["PETG white"]},
  {id:"c",items:[],rule:{vendor:"eryone"},excluded:[]}];
out.members=Object.fromEntries(membership(groups,list));
out.fav=favoritesFirst(list,new Set(["TPU"])).map(p=>p.name);
const cfg={groups:{filament:[{id:"g1",name:"PETG",color:"#0ea5e9",items:["x"],collapsed:false,rule:{},excluded:[]}],printer:[],process:[]},
  hidden:{filament:["h1"],printer:[],process:[]},favorites:{filament:[],printer:[],process:[]},not_duplicates:{filament:[],printer:[],process:[]},
  notes:{filament:{x:"mine"},printer:{},process:{}},favorites_first:true};
const exported=JSON.stringify(exportConfig(cfg,"0.2.0","2026-10-27"));
const inc=parseImport(JSON.stringify({format:"preset-groups",groups:{filament:[{id:"g1",name:"petg",items:["x","y"],rule:{type:"PETG"}},
  {id:"g9",name:"Flex",items:["z"]}]},hidden:{filament:["h2"]},notes:{filament:{x:"theirs",z:"tpu"}}}));
const merged=mergeImport(cfg,inc,"merge");
out.merged={groups:merged.groups.filament.map(g=>[g.name,g.items,g.rule]),hidden:merged.hidden.filament,notes:merged.notes.filament,
  untouched:cfg.groups.filament[0].items};
const replaced=mergeImport(cfg,inc,"replace");
out.replaced={groups:replaced.groups.filament.map(g=>g.name),hidden:replaced.hidden.filament,notes:replaced.notes.filament,printer:replaced.groups.printer};
out.roundTrip=importSummary(parseImport(exported));
try{parseImport('{"groups":{}}');out.bad="accepted"}catch(e){out.bad="refused"}
console.log(JSON.stringify(out));
"""

    def test_rules_membership_and_import(self):
        node = shutil.which("node")
        if node is None:
            self.skipTest("Node.js is not installed")
        with open(os.path.join(ROOT, "page.html"), encoding="utf-8") as stream:
            page = stream.read()
        pure = re.search(r"/\* PURE:BEGIN.*?\*/(.*)/\* PURE:END \*/", page, re.S).group(1)
        result = subprocess.run([node, "-"], input=pure + self.HARNESS, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)
        out = json.loads(result.stdout)
        self.assertTrue(out["type"])
        self.assertEqual(out["vendor"], ["PETG black", "PETG white"])
        self.assertEqual(out["anyOf"], ["PLA red", "TPU"])
        self.assertEqual(out["both"], ["PETG white"])
        self.assertEqual(out["printer"], ["PETG black", "PETG white", "PLA red"])
        self.assertFalse(out["empty"])
        # By hand first, then the first matching rule; a preset taken out by hand stays out.
        self.assertEqual(out["members"], {"PLA red": "a", "PETG black": "b", "TPU": "c"})
        self.assertEqual(out["fav"][0], "TPU")
        merged = out["merged"]
        self.assertEqual(merged["groups"], [["PETG", ["x", "y"], {"type": "PETG"}], ["Flex", ["z"], {}]])
        self.assertEqual(merged["hidden"], ["h1", "h2"])
        self.assertEqual(merged["notes"], {"x": "mine", "z": "tpu"})
        self.assertEqual(merged["untouched"], ["x"])
        replaced = out["replaced"]
        self.assertEqual((replaced["groups"], replaced["hidden"], replaced["notes"]), (["petg", "Flex"], ["h2"], {"x": "theirs", "z": "tpu"}))
        self.assertEqual(replaced["printer"], [])
        self.assertEqual(out["roundTrip"], {"groups": 1, "favorites": 0, "hidden": 1, "notes": 1})
        self.assertEqual(out["bad"], "refused")


class Translations(unittest.TestCase):
    def test_placeholders_match(self):
        for key, (en, ru) in pg.STRINGS.items():
            with self.subTest(key=key):
                self.assertEqual(set(re.findall(r"\{(\w+)\}", en)), set(re.findall(r"\{(\w+)\}", ru)))

    def test_plural_forms(self):
        for key, (en, ru) in pg.STRINGS.items():
            if "|" in en or "|" in ru:
                with self.subTest(key=key):
                    self.assertEqual((len(en.split("|")), len(ru.split("|"))), (2, 3))

    def test_every_key_the_page_and_plugin_use_exists(self):
        with open(os.path.join(ROOT, "page.html"), encoding="utf-8") as stream:
            page = stream.read()
        with open(os.path.join(ROOT, "presetgroups.py"), encoding="utf-8") as stream:
            glue = stream.read()
        used = set(re.findall(r"""\b(?:t|plural)\(\s*["']([\w.]+)["']""", page))
        used |= set(re.findall(r'data-(?:t|tip)="([\w.]+)"', page))
        used |= set(re.findall(r'_t\(\s*"([\w.]+)"', glue))
        # Keys picked by a condition: t(on?"msg.fav":"msg.unfav").
        pairs = re.findall(r"""\?\s*["']([a-z]+\.[\w.]+)["']\s*:\s*["']([a-z]+\.[\w.]+)["']""", page)
        used |= {key for pair in pairs for key in pair}
        # Keys the page builds from parts.
        parts = {"kind.": pg.KINDS, "empty.none_": pg.KINDS, "dlg.text_": pg.KINDS, "dlg.placeholder_": pg.KINDS,
                 "drawer.note_ph_": pg.KINDS, "lang.": ("auto", "ru", "en"), "theme.": pg.THEMES, "rf.": pg.RULE_KEYS,
                 "issue.": ("orphan", "no_printer"), "health.": ("orphan", "no_printer"),
                 "nav.": ("all", "none", "new", "fav", "dups", "spool", "health", "hidden")}
        used = {k for k in used if k not in parts}
        self.assertEqual(sorted(k for k in used if k not in pg.STRINGS), [])
        for prefix, suffixes in parts.items():
            for suffix in suffixes:
                self.assertIn(prefix + suffix, pg.STRINGS)


class Build(unittest.TestCase):
    def test_wheel_module_is_one_valid_file(self):
        spec = importlib.util.spec_from_file_location("build_wheel", os.path.join(ROOT, "build_wheel.py"))
        build = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(build)
        source = build.build_module()
        self.assertNotIn("BUILD:CORE", source)
        self.assertNotIn('r"""BUILD:PAGE"""', source)
        compile(source, "presetgroups/__init__.py", "exec")
        with tempfile.TemporaryDirectory() as folder:
            path = os.path.join(folder, "built.py")
            with open(path, "w", encoding="utf-8") as stream:
                stream.write(source)
            spec = importlib.util.spec_from_file_location("built", path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            self.assertTrue(module.PAGE.startswith("<!doctype html>"))
            self.assertEqual(module._page(), module.PAGE)
            self.assertEqual(module.VERSION, pg.VERSION)

    def test_page_script_parses(self):
        node = None
        for candidate in ("node", "node.exe"):
            try:
                subprocess.run([candidate, "--version"], capture_output=True, check=True)
                node = candidate
                break
            except (OSError, subprocess.CalledProcessError):
                continue
        if node is None:
            self.skipTest("Node.js is not installed")
        with open(os.path.join(ROOT, "page.html"), encoding="utf-8") as stream:
            script = re.search(r"<script>(.*)</script>", stream.read(), re.S).group(1)
        result = subprocess.run([node, "--check", "-"], input=script, capture_output=True, text=True, encoding="utf-8")
        self.assertEqual(result.returncode, 0, result.stderr)


if __name__ == "__main__":
    unittest.main()

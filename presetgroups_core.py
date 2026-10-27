"""Preset Groups: the logic that needs no running OrcaSlicer.

build_wheel.py joins this file, the page (page.html) and the plugin glue (presetgroups.py) into
one module, so Orca loads a single file. Nothing here imports orca, which keeps it testable.
"""

import hashlib
import json
import re


VERSION = "0.2.0"
KINDS = ("filament", "printer", "process")
MAX_GROUPS = 60
MAX_GROUP_NAME = 48
MAX_NEAR_KEYS = 4
MAX_PARENT_DIFF = 60
MAX_COMPARE_ROWS = 400
MAX_NOTE = 500
MAX_RULE = 60
# What a group rule can match on; a rule with several fields needs all of them.
RULE_KEYS = ("type", "vendor", "model", "printer", "text")
THEMES = ("auto", "warm", "night")
GROUP_COLORS = ("#0ea5e9", "#10b981", "#f59e0b", "#ef4444", "#8b5cf6", "#ec4899", "#14b8a6", "#64748b")

# Keys that name a preset or tie it to other presets. Two presets that differ only here have the
# same settings.
IDENTITY_KEYS = {
    "name", "inherits", "alias", "renamed_from", "from", "version", "updated_time", "setting_id", "base_id",
    "filament_id", "filament_settings_id", "print_settings_id", "printer_settings_id", "instantiation",
    "is_custom_defined", "compatible_printers", "compatible_printers_condition", "compatible_prints",
    "compatible_prints_condition", "default_filament_profile", "default_print_profile",
}

# What each list shows about a preset, by kind: (field, keys tried in order).
FACTS = {
    "filament": [
        ("type", ("filament_type",)),
        ("vendor", ("filament_vendor",)),
        # A preset keeps its own colour in default_filament_colour; filament_colour belongs to the project.
        ("color", ("default_filament_colour", "filament_colour")),
        ("nozzle", ("nozzle_temperature",)),
        ("bed", ("hot_plate_temp", "textured_plate_temp", "eng_plate_temp", "cool_plate_temp")),
        ("flow", ("filament_flow_ratio",)),
        ("speed", ("filament_max_volumetric_speed",)),
        ("pa", ("pressure_advance",)),
    ],
    "printer": [
        ("model", ("printer_model",)),
        ("nozzle", ("nozzle_diameter",)),
        ("area", ("printable_area",)),
        ("height", ("printable_height",)),
    ],
    "process": [
        ("layer", ("layer_height",)),
        ("walls", ("wall_loops",)),
        ("infill", ("sparse_infill_density",)),
        ("pattern", ("sparse_infill_pattern",)),
        ("support", ("enable_support",)),
    ],
}

# PipSpool names the presets it creates "(#29) PETG Black - StarPlast - PipSpool".
PIPSPOOL_NAME = re.compile(r"^\(#\d+\)\s.*\bpipspool\s*$", re.I)


def split_values(serialized):
    """Values of a serialized Orca vector option. Orca quotes only the values that need it
    (escape_strings_cstyle), so 'PLA;"Qidi Q1 Pro 0.4 nozzle"' and '220;225' both occur."""
    if serialized is None:
        return []
    text = str(serialized)
    if not text:
        return []
    values, current, quoted, escaped = [], [], False, False
    for char in text:
        if escaped:
            current.append({"n": "\n", "r": "\r"}.get(char, char))
            escaped = False
        elif char == "\\" and quoted:
            escaped = True
        elif char == '"':
            quoted = not quoted
        elif char == ";" and not quoted:
            values.append("".join(current))
            current = []
        else:
            current.append(char)
    values.append("".join(current))
    return values


def first_value(serialized):
    values = split_values(serialized)
    return values[0].strip() if values else ""


def vendor_key(vendor):
    """Spellings of one vendor ("FDPlast  ", "fdplast", "FDplast") share a key."""
    return re.sub(r"[\s._-]+", "", str(vendor or "")).casefold()


def source_of(name):
    return "pipspool" if PIPSPOOL_NAME.match(str(name or "")) else "own"


def bed_size(area):
    """'0x0,245x0,245x245,0x245' -> '245×245'."""
    xs, ys = [], []
    for point in re.split(r"[,;]", str(area or "")):
        match = re.match(r"\s*(-?[\d.]+)\s*x\s*(-?[\d.]+)\s*$", point)
        if match:
            xs.append(float(match.group(1)))
            ys.append(float(match.group(2)))
    if len(xs) < 3:
        return ""
    return f"{max(xs) - min(xs):g}×{max(ys) - min(ys):g}"


def facts_of(kind, values):
    """The short facts a row shows, from a {key: serialized value} map."""
    facts = {}
    for field, keys in FACTS[kind]:
        value = ""
        for key in keys:
            value = first_value(values.get(key))
            if value and value != "0":
                break
        if field == "area":
            value = bed_size(values.get("printable_area"))
        elif field == "color":
            value = value if re.match(r"^#[0-9a-fA-F]{6}([0-9a-fA-F]{2})?$", value) else ""
        facts[field] = value
    return facts


def fingerprint(values):
    body = {k: v for k, v in values.items() if k not in IDENTITY_KEYS}
    return hashlib.sha1(json.dumps(body, sort_keys=True, ensure_ascii=False).encode("utf-8")).hexdigest()


def differing_keys(a, b, limit=None):
    keys = sorted((set(a) | set(b)) - IDENTITY_KEYS)
    out = []
    for key in keys:
        if a.get(key) != b.get(key):
            out.append(key)
            if limit is not None and len(out) > limit:
                break
    return out


def parent_changes(values, parent_values):
    """Settings a preset changes from its parent: [{key, value, parent}]."""
    if not parent_values:
        return []
    changes = []
    for key in differing_keys(values, parent_values):
        changes.append({"key": key, "value": str(values.get(key, ""))[:120], "parent": str(parent_values.get(key, ""))[:120]})
        if len(changes) >= MAX_PARENT_DIFF:
            break
    return changes


def health_issues(kind, parent_name, parent_found, printers, known_printers):
    """What is wrong with a preset: "orphan" when its base preset is gone, "no_printer" when every
    printer it is made for is gone (Orca then shows it for none of them)."""
    issues = []
    if parent_name and not parent_found:
        issues.append("orphan")
    if kind != "printer" and printers and known_printers is not None and not any(p in known_printers for p in printers):
        issues.append("no_printer")
    return issues


def compare_presets(names, values_by_name):
    """The settings in which the given presets differ: {"rows": [{key, values}], "same", "truncated"}.

    values follow the order of names; the base preset ("inherits") comes first, since a different
    base explains many of the other differences."""
    keys = set()
    for name in names:
        keys.update(values_by_name.get(name, {}))
    keys -= IDENTITY_KEYS - {"inherits"}
    rows, same = [], 0
    for key in sorted(keys, key=lambda k: (k != "inherits", k)):
        column = [str(values_by_name.get(name, {}).get(key, "")) for name in names]
        if len(set(column)) == 1:
            same += 1
            continue
        rows.append({"key": key, "values": [value[:200] for value in column]})
    return {"rows": rows[:MAX_COMPARE_ROWS], "same": same, "truncated": len(rows) > MAX_COMPARE_ROWS}


def build_record(kind, name, label, values, parent_name, parent_values, own_printers, parent_printers,
                 compatible_now, selected, parent_now="", known_printers=None):
    """One preset as the page sees it.

    parent_now is the name Orca found the base preset under ("" when it is gone); it differs from
    parent_name when Orca renamed its system preset. known_printers are the printer presets the user
    has, or None when that is unknown."""
    printers = [p for p in (own_printers or parent_printers or []) if p]
    return {
        "issues": health_issues(kind, parent_name, parent_now, printers, known_printers),
        "parent_now": parent_now if parent_now and parent_now != parent_name else "",
        "kind": kind,
        "name": name,
        "label": label or name,
        "parent": parent_name or "",
        "source": source_of(name),
        "printers": printers,
        "compatible": bool(compatible_now),
        "selected": selected,
        "facts": facts_of(kind, values),
        "changes": parent_changes(values, parent_values),
        "fingerprint": fingerprint(values),
    }


class _Union:
    def __init__(self, items):
        self.parent = {item: item for item in items}

    def find(self, item):
        while self.parent[item] != item:
            self.parent[item] = self.parent[self.parent[item]]
            item = self.parent[item]
        return item

    def join(self, a, b):
        self.parent[self.find(a)] = self.find(b)


def find_duplicates(kind, records, values_by_name, dismissed=()):
    """Groups of presets that look like one preset saved several times.

    Two presets are linked when they have identical settings apart from names and links, or the
    same base (for filament: the same type and vendor) with at most MAX_NEAR_KEYS different
    settings, or are a PipSpool preset and an own preset with the same vendor, type and colour.
    Filaments of different colours are never linked: they are different spools. Linked presets form
    one cluster; its reason is "same" when all of them have identical settings, "near" when some
    differ in a few settings, else "spool". A cluster the user marked "not duplicates" (its sorted
    names joined by "\\n") is left out.
    """
    dismissed = set(dismissed or ())
    union = _Union([r["name"] for r in records])
    by_print = {}
    for record in records:
        first = by_print.setdefault(record["fingerprint"], record["name"])
        union.join(record["name"], first)

    def candidate_key(record):
        facts = record["facts"]
        if kind == "filament":
            return (facts.get("type", "").casefold(), vendor_key(facts.get("vendor")))
        return (record["parent"],)

    buckets = {}
    for record in records:
        buckets.setdefault(candidate_key(record), []).append(record)
    links = []
    for bucket in buckets.values():
        if len(bucket) < 2 or len(bucket) > 80:
            continue
        for i, a in enumerate(bucket):
            for b in bucket[i + 1:]:
                if a["fingerprint"] == b["fingerprint"]:
                    continue
                colours = (a["facts"].get("color", "").lower(), b["facts"].get("color", "").lower())
                if kind == "filament" and all(colours) and colours[0] != colours[1]:
                    # Two colours of one material are two spools, not one preset saved twice.
                    continue
                diff = differing_keys(values_by_name[a["name"]], values_by_name[b["name"]], MAX_NEAR_KEYS)
                if len(diff) <= MAX_NEAR_KEYS:
                    links.append((a["name"], "near", diff))
                elif kind == "filament" and a["source"] != b["source"] and colours[0] and colours[0] == colours[1]:
                    links.append((a["name"], "spool", []))
                else:
                    continue
                union.join(a["name"], b["name"])
    members = {}
    for record in records:
        members.setdefault(union.find(record["name"]), []).append(record)
    reasons, keys = {}, {}
    for name, reason, diff in links:
        root = union.find(name)
        keys.setdefault(root, set()).update(diff)
        if reasons.get(root) != "near":
            reasons[root] = reason
    clusters = []
    for root, group in members.items():
        if len(group) < 2:
            continue
        names = sorted(r["name"] for r in group)
        if len({r["fingerprint"] for r in group}) == 1:
            cluster = {"kind": kind, "reason": "same", "names": names, "keys": []}
        else:
            cluster = {"kind": kind, "reason": reasons.get(root, "near"), "names": names, "keys": sorted(keys.get(root, ()))}
        if "\n".join(names) not in dismissed:
            clusters.append(cluster)
    clusters.sort(key=lambda c: ({"same": 0, "near": 1, "spool": 2}[c["reason"]], c["names"]))
    return clusters


def _strings(raw):
    """A list of non-empty strings without repeats, in order."""
    seen, out = set(), []
    for item in raw if isinstance(raw, list) else []:
        item = str(item)
        if item and item not in seen:
            seen.add(item)
            out.append(item)
    return out


def clean_rule(raw):
    """A group rule: {field: text} for the RULE_KEYS that are set."""
    raw = raw if isinstance(raw, dict) else {}
    rule = {}
    for key in RULE_KEYS:
        value = re.sub(r"\s+", " ", str(raw.get(key) or "")).strip()[:MAX_RULE]
        if value:
            rule[key] = value
    return rule


def clean_groups(raw):
    """Validate the groups the page sends: {kind: [{id, name, color, items, rule, excluded}]}.

    items are the presets put into the group by hand; each name belongs to one group only. Names
    of presets that do not exist now are kept, since a preset may come back (another account, a
    restored file). rule fills the group with matching presets; excluded are the presets taken
    out of it by hand although the rule matches them.
    """
    clean = {}
    raw = raw if isinstance(raw, dict) else {}
    for kind in KINDS:
        groups, used_ids, used_items = [], set(), set()
        for group in raw.get(kind, []) if isinstance(raw.get(kind), list) else []:
            if not isinstance(group, dict) or len(groups) >= MAX_GROUPS:
                continue
            name = re.sub(r"\s+", " ", str(group.get("name", ""))).strip()[:MAX_GROUP_NAME]
            if not name:
                continue
            gid = re.sub(r"[^A-Za-z0-9_-]", "", str(group.get("id", "")))[:24]
            if not gid or gid in used_ids:
                gid = "g" + hashlib.sha1(f"{kind}:{name}:{len(groups)}".encode("utf-8")).hexdigest()[:10]
            used_ids.add(gid)
            color = str(group.get("color", ""))
            if color not in GROUP_COLORS:
                color = GROUP_COLORS[len(groups) % len(GROUP_COLORS)]
            items = [item for item in _strings(group.get("items")) if item not in used_items]
            used_items.update(items)
            groups.append({"id": gid, "name": name, "color": color, "items": items,
                           "collapsed": bool(group.get("collapsed", False)),
                           "rule": clean_rule(group.get("rule")), "excluded": _strings(group.get("excluded"))})
        clean[kind] = groups
    return clean


def clean_names(raw):
    """{kind: [names]} with strings only and no repeats."""
    raw = raw if isinstance(raw, dict) else {}
    return {kind: _strings(raw.get(kind)) for kind in KINDS}


def clean_notes(raw):
    """{kind: {name: note}} without empty notes."""
    raw = raw if isinstance(raw, dict) else {}
    out = {}
    for kind in KINDS:
        notes = raw.get(kind) if isinstance(raw.get(kind), dict) else {}
        out[kind] = {str(name): str(text).strip()[:MAX_NOTE] for name, text in notes.items()
                     if str(name) and str(text or "").strip()}
    return out


DEFAULT_CONFIG = {"groups": {k: [] for k in KINDS}, "hidden": {k: [] for k in KINDS},
                  "not_duplicates": {k: [] for k in KINDS}, "favorites": {k: [] for k in KINDS},
                  "notes": {k: {} for k in KINDS}, "seen": {k: [] for k in KINDS}, "seen_ready": False,
                  "favorites_first": True, "language": "auto", "theme": "auto"}


def clean_config(value):
    value = value if isinstance(value, dict) else {}
    return {
        "groups": clean_groups(value.get("groups")),
        "hidden": clean_names(value.get("hidden")),
        "not_duplicates": clean_names(value.get("not_duplicates")),
        "favorites": clean_names(value.get("favorites")),
        "notes": clean_notes(value.get("notes")),
        # Presets the user has seen, so new ones can be shown; seen_ready is False until the page
        # has recorded the presets that existed when the plugin was first opened.
        "seen": clean_names(value.get("seen")),
        "seen_ready": bool(value.get("seen_ready", False)),
        "favorites_first": bool(value.get("favorites_first", True)),
        "language": value.get("language") if value.get("language") in ("auto", "en", "ru") else "auto",
        "theme": value.get("theme") if value.get("theme") in THEMES else "auto",
    }

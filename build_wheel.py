"""Build the Preset Groups plugin wheel for OrcaSlicer.

Joins presetgroups.py, presetgroups_core.py and page.html into one module (Orca loads a single
file) and writes dist/presetgroups-<version>-py3-none-any.whl plus dist/presetgroups_any.whl, the
name Orca Cloud expects.
"""

import base64
import csv
import hashlib
import io
from pathlib import Path
import re
import shutil
import zipfile


ROOT = Path(__file__).resolve().parent
CORE_LINE = "from presetgroups_core import *  # noqa: F401,F403  # BUILD:CORE"


def build_module():
    glue = (ROOT / "presetgroups.py").read_text(encoding="utf-8")
    core = (ROOT / "presetgroups_core.py").read_text(encoding="utf-8")
    page = (ROOT / "page.html").read_text(encoding="utf-8")
    if CORE_LINE not in glue or 'PAGE = r"""BUILD:PAGE"""' not in glue:
        raise SystemExit("presetgroups.py lost its build markers")
    if '"""' in page or page.rstrip().endswith("\\"):
        raise SystemExit('page.html must not contain """ or end with a backslash')
    core_body = core.split('"""', 2)[2].lstrip("\n")  # drop the module docstring
    module = glue.replace(CORE_LINE, "# ---- presetgroups_core.py ----\n" + core_body.rstrip() + "\n# ---- end of presetgroups_core.py ----")
    module = module.replace('PAGE = r"""BUILD:PAGE"""', 'PAGE = r"""' + page + '"""')
    return module


def main():
    module = build_module().encode("utf-8")
    version = re.search(rb'^VERSION = "([^"]+)"', module, re.M).group(1).decode("ascii")
    header = re.search(rb'^# version = "([^"]+)"', module, re.M).group(1).decode("ascii")
    if header != version:
        raise SystemExit(f"Plugin header says {header}, VERSION says {version}")
    dist_info = f"presetgroups-{version}.dist-info"
    output = ROOT / "dist" / f"presetgroups-{version}-py3-none-any.whl"
    cloud_output = ROOT / "dist" / "presetgroups_any.whl"
    files = {
        "presetgroups/__init__.py": module,
        "presetgroups/presetgroups.svg": (ROOT / "presetgroups.svg").read_bytes(),
        f"{dist_info}/METADATA": (
            "Metadata-Version: 2.4\n"
            "Name: presetgroups\n"
            f"Version: {version}\n"
            "Summary: OrcaSlicer plugin: sort your own presets into groups with any names and find the ones saved twice.\n"
            "Author: GNUGiminot\n"
            "License-Expression: MIT\n"
            "Requires-Python: >=3.9\n\n"
        ).encode("utf-8"),
        f"{dist_info}/WHEEL": (
            "Wheel-Version: 1.0\n"
            "Generator: Preset Groups build_wheel.py\n"
            "Root-Is-Purelib: true\n"
            "Tag: py3-none-any\n\n"
        ).encode("utf-8"),
        f"{dist_info}/top_level.txt": b"presetgroups\n",
        f"{dist_info}/licenses/LICENSE": (ROOT / "LICENSE").read_bytes(),
    }
    record = io.StringIO(newline="")
    writer = csv.writer(record, lineterminator="\n")
    for name, content in files.items():
        digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).rstrip(b"=").decode("ascii")
        writer.writerow((name, "sha256=" + digest, len(content)))
    writer.writerow((f"{dist_info}/RECORD", "", ""))
    files[f"{dist_info}/RECORD"] = record.getvalue().encode("utf-8")

    output.parent.mkdir(exist_ok=True)
    with zipfile.ZipFile(output, "w", compression=zipfile.ZIP_DEFLATED) as wheel:
        for name, content in files.items():
            # Fixed timestamps make the wheel byte-for-byte reproducible.
            info = zipfile.ZipInfo(name, date_time=(2026, 1, 1, 0, 0, 0))
            info.compress_type = zipfile.ZIP_DEFLATED
            wheel.writestr(info, content)
    shutil.copyfile(output, cloud_output)
    print(output)
    print(cloud_output)


if __name__ == "__main__":
    main()

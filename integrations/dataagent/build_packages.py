"""Assemble standalone skills and the admin-installed plugin, using only stdlib."""

import argparse
import json
from pathlib import Path
import shutil
import tempfile
from zipfile import ZIP_DEFLATED, ZipFile

BASE = Path(__file__).resolve().parent
SKILLS = ("ontology-discovery", "entity-extraction", "semantic-grounding")
EXCLUDED = shutil.ignore_patterns("__pycache__", "*.pyc", ".pytest_cache", ".DS_Store", "tests", "offline_budget.py")


def assemble_skill(name, destination):
    if name not in SKILLS:
        raise ValueError(f"Unknown skill: {name}")
    shutil.copytree(BASE / "skills" / name, destination, ignore=EXCLUDED)
    shutil.copytree(BASE / "shared", destination, dirs_exist_ok=True, ignore=EXCLUDED)


def archive(directory, output):
    with ZipFile(output, "w", ZIP_DEFLATED) as package:
        for path in sorted(directory.rglob("*")):
            if path.is_file():
                package.write(path, path.relative_to(directory.parent))


def build(output):
    output = Path(output)
    output.mkdir(parents=True, exist_ok=True)
    manifest = json.loads((BASE / "plugin.json").read_bytes())
    if [skill["name"] for skill in manifest["skills"]] != list(SKILLS):
        raise ValueError("Manifest and build skill lists differ")
    with tempfile.TemporaryDirectory(prefix="ontofoundry-package-") as scratch:
        root = Path(scratch)
        plugin = root / "ontofoundry-dataagent"
        (plugin / "skills").mkdir(parents=True)
        for name in SKILLS:
            target = plugin / "skills" / name
            assemble_skill(name, target)
            archive(target, output / f"{name}.zip")
        shutil.copytree(BASE / "agents", plugin / "agents", ignore=EXCLUDED)
        for filename in ("plugin.json", "install.sh", "迁移说明.md"):
            shutil.copy2(BASE / filename, plugin / filename)
        archive(plugin, output / "ontofoundry-dataagent-plugin.zip")
    return [output / f"{name}.zip" for name in SKILLS] + [output / "ontofoundry-dataagent-plugin.zip"]


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="组装三个独立技能包和管理员插件包")
    parser.add_argument("--output-dir", type=Path, default=BASE / "dist")
    args = parser.parse_args()
    for path in build(args.output_dir):
        print(path)

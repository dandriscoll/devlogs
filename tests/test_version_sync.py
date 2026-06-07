"""Guard against version drift across the published package manifests.

devlogs ships three packages from one repo: the Python package (pyproject.toml,
the source of truth), and two npm packages — devlogs-browser (browser/) and
devlogs-node (node/). `publish/release.sh` bumps all three together; this test
fails if any manifest is left behind (the failure shape that shipped a 2.4.5
GitHub release while devlogs-node stayed at 2.4.4).
"""

import json
import os
import re

PROJECT_ROOT = os.path.dirname(os.path.dirname(__file__))


def _pyproject_version():
	with open(os.path.join(PROJECT_ROOT, "pyproject.toml"), encoding="utf-8") as fh:
		for line in fh:
			m = re.match(r'\s*version\s*=\s*"([^"]+)"', line)
			if m:
				return m.group(1)
	raise AssertionError("no version found in pyproject.toml")


def _package_json_version(relpath):
	with open(os.path.join(PROJECT_ROOT, relpath), encoding="utf-8") as fh:
		return json.load(fh)["version"]


def test_all_published_manifests_share_one_version():
	source_of_truth = _pyproject_version()
	manifests = {
		"browser/package.json": _package_json_version("browser/package.json"),
		"node/package.json": _package_json_version("node/package.json"),
	}
	mismatched = {p: v for p, v in manifests.items() if v != source_of_truth}
	assert not mismatched, (
		f"version drift from pyproject.toml ({source_of_truth}): {mismatched}. "
		f"Bump every manifest together (publish/release.sh does this)."
	)

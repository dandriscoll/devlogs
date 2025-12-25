# Level normalization helpers.

from typing import Optional


def normalize_level(level: Optional[str]) -> Optional[str]:
	if level is None:
		return None
	if not isinstance(level, str):
		level = str(level)
	level = level.strip().lower()
	return level or None

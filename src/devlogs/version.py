import os


def _resolve_version():
    env = os.environ.get("BUILD_VERSION")
    if env:
        return env
    try:
        from ._version_static import __version__ as static
        return static
    except ImportError:
        return "development"


__version__ = _resolve_version()

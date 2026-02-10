# Output plugin model for the collector
#
# Plugins allow the collector to write enriched log records to backends
# beyond the built-in OpenSearch ingestor. Each plugin declares URL schemes
# it handles (e.g., "loki" for loki:// URLs) and receives validated,
# enriched DevlogsRecord objects.
#
# Built-in modes (forward via http/https, ingest to OpenSearch) are NOT
# plugins -- they continue to work as before. Plugins extend the collector
# with new URL-scheme-based output backends.
#
# Configuration:
#   Set DEVLOGS_FORWARD_URL to a plugin URL scheme:
#     DEVLOGS_FORWARD_URL=loki://loki-host:3100
#
#   The collector will validate and enrich records as usual, then call
#   the plugin's send() method instead of forwarding raw bytes.

from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional, Type

from .schema import DevlogsRecord


class OutputPlugin(ABC):
    """Base class for collector output plugins.

    Subclass this to add a new output backend to the collector.
    The collector calls send() with enriched records when DEVLOGS_FORWARD_URL
    matches one of the plugin's declared schemes.

    Class attributes:
        name: Human-readable plugin name (e.g., "loki")
        schemes: URL schemes this plugin handles, without "://" (e.g., ["loki", "lokis"])
    """

    name: str = ""
    schemes: List[str] = []

    @abstractmethod
    def __init__(self, url: str, cfg: Any):
        """Initialize the plugin with the target URL and collector config.

        Args:
            url: The full URL from DEVLOGS_FORWARD_URL (e.g., "loki://host:3100")
            cfg: The DevlogsConfig instance
        """
        ...

    @abstractmethod
    def send(self, records: List[DevlogsRecord]) -> Dict[str, Any]:
        """Send enriched records to the backend.

        Args:
            records: List of validated, enriched DevlogsRecord objects

        Returns:
            Dict with at least {"ingested": <count>}

        Raises:
            PluginError on failure
        """
        ...

    @abstractmethod
    def check(self) -> str:
        """Check connectivity to the backend.

        Returns:
            Human-readable status string (e.g., "Loki: OK")

        Raises:
            Exception if connectivity check fails
        """
        ...

    @abstractmethod
    def display_info(self) -> str:
        """Return human-readable connection info for CLI display.

        Example: "Loki: loki://loki-host:3100"
        """
        ...


# Plugin registry: URL scheme -> plugin class
_registry: Dict[str, Type[OutputPlugin]] = {}


def register_plugin(plugin_class: Type[OutputPlugin]):
    """Register an output plugin for its URL schemes.

    Call this after defining your plugin class:

        class LokiPlugin(OutputPlugin):
            name = "loki"
            schemes = ["loki", "lokis"]
            ...

        register_plugin(LokiPlugin)

    Args:
        plugin_class: A subclass of OutputPlugin

    Raises:
        ValueError: If schemes list is empty or plugin_class is invalid
    """
    if not getattr(plugin_class, "schemes", None):
        raise ValueError(
            f"Plugin {plugin_class.__name__} must define a non-empty 'schemes' list"
        )
    for scheme in plugin_class.schemes:
        _registry[scheme.lower()] = plugin_class


def get_plugin_for_url(url: str, cfg: Any) -> Optional[OutputPlugin]:
    """Look up and instantiate a plugin for the given URL.

    Returns None if no plugin handles the URL's scheme, meaning the
    URL should be handled by the built-in forward mode (http/https).

    Args:
        url: The URL to match (e.g., "loki://host:3100")
        cfg: DevlogsConfig instance passed to the plugin constructor

    Returns:
        An OutputPlugin instance, or None if no plugin matches
    """
    if "://" not in url:
        return None
    scheme = url.split("://", 1)[0].lower()
    plugin_class = _registry.get(scheme)
    if plugin_class is None:
        return None
    return plugin_class(url, cfg)


_SCHEMA_KEYS = {
    "application", "component", "timestamp", "message", "level",
    "area", "operation_id", "environment", "version", "fields",
    "collected_ts", "client_ip", "identity", "doc_type",
}


def dict_to_record(doc: dict) -> DevlogsRecord:
    """Convert a raw log dict to a DevlogsRecord.

    Non-schema fields (e.g. logger, pathname, lineno, process, thread)
    are collected into the fields dict so they aren't lost.

    Args:
        doc: A log record dict as produced by DevlogsHandler or DevlogsClient

    Returns:
        A DevlogsRecord instance
    """
    record = DevlogsRecord(
        application=doc.get("application", "unknown"),
        component=doc.get("component", "default"),
        timestamp=doc.get("timestamp", ""),
        message=doc.get("message"),
        level=doc.get("level"),
        area=doc.get("area"),
        operation_id=doc.get("operation_id"),
        environment=doc.get("environment"),
        version=doc.get("version"),
    )
    fields = dict(doc.get("fields") or {})
    for key, value in doc.items():
        if key not in _SCHEMA_KEYS and value is not None:
            fields[key] = value
    record.fields = fields or None
    return record


def get_registered_schemes() -> List[str]:
    """Return all registered plugin URL schemes."""
    return sorted(_registry.keys())


def list_plugins() -> List[Type[OutputPlugin]]:
    """Return all registered plugin classes (deduplicated)."""
    seen = set()
    result = []
    for cls in _registry.values():
        if id(cls) not in seen:
            seen.add(id(cls))
            result.append(cls)
    return result

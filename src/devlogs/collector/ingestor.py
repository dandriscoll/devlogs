# Ingest logic for the collector
#
# When OpenSearch admin connection is configured (and no forward URL),
# the collector operates in ingest mode: it writes records directly
# to the configured OpenSearch index.

from typing import List, Dict, Any, Optional

from .schema import DevlogsRecord
from .errors import IngestError


def get_target_index(
    record: DevlogsRecord,
    default_index: str,
    index_map: Optional[Dict[str, str]] = None,
) -> str:
    """Determine the target index for a record based on application routing.

    Args:
        record: The record to route
        default_index: Default index if no mapping found
        index_map: Optional mapping from application name to index

    Returns:
        Target index name
    """
    if index_map and record.application in index_map:
        return index_map[record.application]
    return default_index


def ingest_records(
    client: Any,  # LightweightOpenSearchClient
    index_name: str,
    records: List[DevlogsRecord],
    index_map: Optional[Dict[str, str]] = None,
) -> Dict[str, Any]:
    """Ingest a list of records into OpenSearch.

    Uses bulk API for efficiency when multiple records are present.
    Supports per-application index routing via index_map.

    Args:
        client: OpenSearch client instance
        index_name: Default target index name
        records: List of enriched DevlogsRecord objects
        index_map: Optional mapping from application name to index name

    Returns:
        Dict with ingestion statistics

    Raises:
        IngestError: If ingestion fails
    """
    if not records:
        return {"ingested": 0}

    try:
        if len(records) == 1:
            # Single record - use simple index
            doc = records[0].to_dict()
            target_index = get_target_index(records[0], index_name, index_map)
            client.index(index=target_index, body=doc)
            return {"ingested": 1}
        else:
            # Multiple records - use bulk API with per-record routing
            bulk_body = []
            for record in records:
                target_index = get_target_index(record, index_name, index_map)
                # Action line with target index
                bulk_body.append({"index": {"_index": target_index}})
                # Document line
                bulk_body.append(record.to_dict())

            result = client.bulk(body=bulk_body)

            # Check for errors
            if result.get("errors"):
                error_items = [
                    item for item in result.get("items", [])
                    if "error" in item.get("index", {})
                ]
                if error_items:
                    first_error = error_items[0]["index"]["error"]
                    raise IngestError(
                        "BULK_ERROR",
                        f"Bulk ingest partially failed: {first_error.get('reason', 'Unknown error')}"
                    )

            return {"ingested": len(records)}

    except IngestError:
        raise
    except Exception as e:
        raise IngestError(
            "OPENSEARCH_ERROR",
            f"Failed to ingest records: {str(e)}"
        )


def build_opensearch_document(record: DevlogsRecord) -> Dict[str, Any]:
    """Convert an DevlogsRecord to an OpenSearch document.

    This adds any additional fields needed for OpenSearch indexing.

    Args:
        record: The enriched record

    Returns:
        Document ready for indexing
    """
    doc = record.to_dict()
    # Add doc_type for compatibility with existing devlogs schema
    doc["doc_type"] = "devlogs_record"
    return doc

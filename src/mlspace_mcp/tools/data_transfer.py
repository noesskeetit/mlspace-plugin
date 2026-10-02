"""``mlspace_data_transfer`` — manage MLSpace data-transfer connectors, transfers, and history.

Pure declarative data (see ``inference.py`` exemplar). The core owns all request
mechanics. Spans API versions v2/v3/v4/v5; paths are copied verbatim from the
slice, placeholders included.
"""

from __future__ import annotations

from ..registry import DomainTool, Op, Param

ACTIONS: dict[str, Op] = {
    # --- connectors (v3 collection + v2 delete) ---------------------------
    "list_connectors": Op(
        "GET", "/public/v2/data_transfer/v3/connectors",
        # page/page_size are the ONLY working shrink lever for this ~27KB list: the
        # API ignores limit/offset here (limit=5&offset=0 still returned all 65). No
        # auto-default page_size — the response has no total_count, so a silent clamp
        # would hide data (breaks principle #1). Pagination stays strictly opt-in.
        query_params={"page": "page", "page_size": "page_size"},
        kind="list",
        help="List all connectors (system, personal, public) in the workspace.",
    ),
    "get_connector": Op(
        "GET", "/public/v2/data_transfer/v3/connectors/{connector_type}/{id_}",
        path_params={"connector_type": "connector_type", "id_": "id_"},
        required=("connector_type", "id_"),
        help="Get one connector by type and id.",
    ),
    "create_connector": Op(
        "POST", "/public/v2/data_transfer/v3/connectors",
        body_field="body",
        required=("body",),
        write=True,
        help="Create a connector; `body` = ConnectorInputViewModelV3.",
    ),
    "update_connector": Op(
        "POST", "/public/v2/data_transfer/v3/connectors/{connector_type}/{id_}",
        path_params={"connector_type": "connector_type", "id_": "id_"},
        body_field="body",
        required=("connector_type", "id_", "body"),
        write=True,
        help="Update a connector; `body` = ConnectorUpdateViewModelV3.",
    ),
    "fav_connector": Op(
        "POST", "/public/v2/data_transfer/v3/connectors/{connector_type}/{id_}/fav",
        path_params={"connector_type": "connector_type", "id_": "id_"},
        body_field="body",
        required=("connector_type", "id_", "body"),
        write=True,
        help="Mark/unmark a connector favorite; `body` = FavoriteInputViewModel.",
    ),
    "halt_connector": Op(
        "POST", "/public/v2/data_transfer/v3/connectors/{connector_type}/{id_}/halt",
        path_params={"connector_type": "connector_type", "id_": "id_"},
        required=("connector_type", "id_"),
        write=True,
        help="Mark a connector inactive (also halts its transfers).",
    ),
    "try_connector": Op(
        "POST", "/public/v2/data_transfer/v3/connectors/{connector_type}/{id_}/try",
        path_params={"connector_type": "connector_type", "id_": "id_"},
        required=("connector_type", "id_"),
        write=True,
        help="Trial-test a connector (connection check; activates the connector on success).",
    ),
    "get_connector_logs": Op(
        "GET", "/public/v2/data_transfer/v3/connectors/{connector_type}/{id_}/try/logs",
        path_params={"connector_type": "connector_type", "id_": "id_"},
        required=("connector_type", "id_"),
        kind="log",
        help="Get connector activation (try) logs.",
    ),
    "delete_connectors": Op(
        "DELETE", "/public/v2/data_transfer/v2/connectors",
        query_params={"ids": "ids"},
        required=("ids",),
        write=True,
        confirm=True,
        help="Delete connectors by id (ids repeat).",
    ),
    "list_sources": Op(
        "GET", "/public/v2/data_transfer/v2/connectors/sources",
        kind="list",
        help="List schemas of all connectors usable as a source.",
    ),
    # --- transfers (v4 reads, v5 writes, v2 delete) -----------------------
    "list_transfers": Op(
        "GET", "/public/v2/data_transfer/v4/transfer",
        kind="list",
        help="List all transfers in the workspace.",
    ),
    "get_transfer": Op(
        "GET", "/public/v2/data_transfer/v4/transfer/{transfer_id}",
        path_params={"transfer_id": "transfer_id"},
        required=("transfer_id",),
        help="Get one transfer by id.",
    ),
    "create_transfer": Op(
        "POST", "/public/v2/data_transfer/v5/transfer",
        body_field="body",
        required=("body",),
        write=True,
        help="Create a transfer; `body` = TransferInputViewModelV5 (runs now unless crontab is set).",
    ),
    "update_transfer": Op(
        "POST", "/public/v2/data_transfer/v5/transfer/{id_}",
        path_params={"id_": "id_"},
        body_field="body",
        required=("id_", "body"),
        write=True,
        help="Update a transfer by id; `body` = TransferInputViewModelV5.",
    ),
    "fav_transfer": Op(
        "POST", "/public/v2/data_transfer/v4/transfer/{id_}/fav",
        path_params={"id_": "id_"},
        body_field="body",
        required=("id_", "body"),
        write=True,
        help="Mark/unmark a transfer favorite; `body` = FavoriteInputViewModel.",
    ),
    "switch_transfer": Op(
        "POST", "/public/v2/data_transfer/v4/transfer/{id_}/switch",
        path_params={"id_": "id_"},
        body_field="body",
        required=("id_", "body"),
        write=True,
        help="Toggle a transfer active/inactive; `body` = StateInputViewModel.",
    ),
    "delete_transfers": Op(
        "DELETE", "/public/v2/data_transfer/v2/transfer",
        query_params={"ids": "ids"},
        required=("ids",),
        write=True,
        confirm=True,
        help="Delete transfers by id (ids repeat).",
    ),
    # --- history (v3 reads, v2/v3 ops, v2 delete) -------------------------
    "list_history": Op(
        "GET", "/public/v2/data_transfer/v3/history",
        query_params={
            "transfer_id": "transfer_id",
            "source_name": "source_name",
            "page": "page",
            "page_size": "page_size",
        },
        kind="list",
        help="List transfer history (paginated; filter by transfer_id/source_name).",
    ),
    "get_history_status": Op(
        "GET", "/public/v2/data_transfer/v3/history/status/stream",
        query_params={"ids": "ids"},
        required=("ids",),
        kind="list",
        help="Get history entries by id (ids repeat).",
    ),
    "get_event_logs": Op(
        "GET", "/public/v2/data_transfer/v2/events/list",
        query_params={
            "offset": "offset",
            "limit": "limit",
            "history_id": "history_id",
            "transfer_id": "transfer_id",
            "event_type": "event_type",
            "event_category": "event_category",
            "as_enum_resolved": "as_enum_resolved",
        },
        required=("offset", "limit"),
        kind="list",
        help="Get transfer event logs (needs offset+limit and either history_id or transfer_id).",
    ),
    "cancel_history": Op(
        "POST", "/public/v2/data_transfer/v2/history/cancel",
        body_field="body",
        required=("body",),
        write=True,
        confirm=True,
        help="Cancel a transfer; `body` = CancelInput.",
    ),
    "rerun_history": Op(
        "POST", "/public/v2/data_transfer/v3/history/rerun",
        body_field="body",
        required=("body",),
        write=True,
        help="Restart a transfer; `body` = RerunInput.",
    ),
    "fav_history": Op(
        "POST", "/public/v2/data_transfer/v2/history/{id_}/fav",
        path_params={"id_": "id_"},
        body_field="favorite",
        required=("id_", "favorite"),
        write=True,
        help="Mark/unmark a history entry favorite; `favorite` is a bare boolean body.",
    ),
    "delete_history": Op(
        "DELETE", "/public/v2/data_transfer/v2/history",
        query_params={"ids": "ids"},
        required=("ids",),
        write=True,
        confirm=True,
        help="Delete history entries by id (ids repeat).",
    ),
}

PARAMS: list[Param] = [
    Param("id_", str, "Entity UUID (connector/transfer/history id, depending on action)."),
    Param("transfer_id", str, "Transfer UUID (get_transfer path; filter for list_history/event logs)."),
    Param(
        "connector_type",
        str,
        "Connector type. Known values: postgresql, mssql, mysql, clickhouse, "
        "oracledb, s3amazon, s3custom, s3google, hdfs, s3mlspace, s3datahub, nfs, "
        "nfsprivate, nfsshared, s3evolution. get_connector accepts the full set; "
        "try/halt/fav/update only the custom subset (the first 8). "
        "Discover live values via list_connectors.",
    ),
    Param("ids", list[str], "List of UUIDs (repeated query) for delete/status actions."),
    Param("source_name", str, "Filter history by source_name (list_history)."),
    Param(
        "page",
        int,
        "Page number (list_history, list_connectors, 1-based). NOTE for list_connectors "
        "the response is a bare array with no total_count, so a short/empty page does "
        "NOT prove the end of the list; list_history instead returns {data, total_count}.",
    ),
    Param("page_size", int, "Page size (list_history, list_connectors)."),
    Param("offset", int, "Pagination offset (get_event_logs)."),
    Param("limit", int, "Pagination limit (get_event_logs)."),
    Param("history_id", str, "History UUID filter (get_event_logs)."),
    Param("event_type", int, "Event type filter (get_event_logs)."),
    Param("event_category", int, "Event category filter (get_event_logs)."),
    Param("as_enum_resolved", bool, "Resolve enum codes to names (get_event_logs)."),
    Param(
        "favorite",
        bool,
        "Favorite flag for fav_history (sent as a bare boolean body, not an object).",
    ),
    Param(
        "body",
        dict,
        "JSON body. create_connector=ConnectorInputViewModelV3; "
        "update_connector=ConnectorUpdateViewModelV3; "
        "fav_connector/fav_transfer=FavoriteInputViewModel {favorite}; "
        "create_transfer/update_transfer=TransferInputViewModelV5; "
        "switch_transfer=StateInputViewModel; cancel_history=CancelInput; "
        "rerun_history=RerunInput {history_id}.",
    ),
]

DOMAIN = DomainTool(
    domain="data_transfer",
    name="mlspace_data_transfer",
    title="MLSpace Data Transfer",
    summary=(
        "Manage MLSpace data-transfer connectors, transfers, and migration history "
        "(create/update/try connectors, run/cancel/rerun transfers, inspect logs)."
    ),
    actions=ACTIONS,
    params=PARAMS,
)

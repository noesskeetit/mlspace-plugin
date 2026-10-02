---
name: mlspace-diagnose-data-transfer
description: "Diagnose a failed / partial data transfer on Cloud.ru MLSpace. Did my data transfer actually fail / land incompletely, and why. Uses the mlspace_data_transfer tools."
license: MIT
compatibility: Requires the `mlspace` MCP server from this plugin (Cloud.ru MLSpace credentials needed).
---

# Diagnose a failed / partial data transfer

Did my data transfer actually fail / land incompletely, and why.

This skill drives the `mlspace` MCP server shipped in the same plugin. If its
tools are not connected, say so instead of guessing — none of these steps can be
carried out any other way.

## Arguments

- `transfer_id` — Transfer id (or give a name).
- `transfer_name` — Transfer name to look up.
- `expected_rows` — Rows you expected, to judge completeness.
- `act` — If true, may rerun a failed run (after confirm).
- `target` — Connected workspace ID or unambiguous name, if scoped.

## Procedure

Goal: determine whether a data transfer truly failed / was partial, and why.
1. Resolve the transfer: if transfer_id given use it, else data_transfer list_transfers
   and match transfer_name.
2. data_transfer list_history (transfer_id, page=1, page_size=20 — this endpoint uses
   page/page_size). Take the latest run's history_id + metrics (size_bytes, rows_count,
   progress, status).
3. data_transfer get_history_status (ids=[history_id]) for the authoritative status
   (in_progress|success|failed|cancelled).
4. If failed/cancelled, data_transfer get_event_logs (history_id, offset=0, limit=50,
   as_enum_resolved=true) for the decoded reason.
5. Compare rows_count/size_bytes vs the user's expectation to judge "partial".
Output: status + hard numbers (rows/bytes/progress) + completeness verdict + decoded
event reasons; separate "genuinely failed" from "clean exit / fewer rows than expected".
Only if act=true: rerun_history (body={history_id}) for a failed run, after confirming.
Caveat: status is only a 4-value enum; "finished but data looks wrong" is inferred from
the numbers, not a dedicated field.

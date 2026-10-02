---
name: mlspace-stage-s3-to-nfs
description: "Stage S3 data to NFS (one-off or nightly) on Cloud.ru MLSpace. Copy/sync S3 -> NFS for a GPU job, optionally on a schedule. Write action. Uses the mlspace_data_transfer tools."
license: MIT
compatibility: Requires the `mlspace` MCP server from this plugin (Cloud.ru MLSpace credentials needed).
---

# Stage S3 data to NFS (one-off or nightly)

Copy/sync S3 -> NFS for a GPU job, optionally on a schedule. Write action.

This skill drives the `mlspace` MCP server shipped in the same plugin. If its
tools are not connected, say so instead of guessing — none of these steps can be
carried out any other way.

## Arguments

- `source_hint` — Which S3 connector/bucket.
- `destination_hint` — Which NFS/cluster connector.
- `source_path` — Path within the source.
- `destination_path` — Path within the NFS share.
- `schedule` — Crontab for nightly runs, e.g. '0 2 * * *'.
- `transfer_name` — Name for the transfer.
- `cluster_name` — Target cluster name (required, not auto-derivable).
- `target` — Connected workspace ID or unambiguous name, if scoped.

## Procedure

Goal: copy/sync S3 -> NFS, optionally on a nightly schedule (write actions;
refused under MLSPACE_READONLY=true).
1. data_transfer list_connectors. SOURCE: an object-storage connector (s3amazon/
   s3custom/s3google). DEST: an NFS/cluster connector. Capture both connector ids.
2. cluster_name is REQUIRED and is NOT readable from the connector — ask the user or
   take it from context; do not guess from get_connector.
3. (optional, S3 only) try_connector to pre-check connectivity (+ its /try/logs).
4. Ensure source_path + destination_path are known (ask if absent). Strategy:
   one-off=write_all; nightly incremental + a crontab schedule (e.g. "0 2 * * *").
5. list_transfers; if one matches this source->dest and the user means "edit", capture
   its id for update instead of create.
6. create_transfer (body=TransferInputViewModelV5: name, connector ids, paths,
   cluster_name, strategy, optional crontab) OR update_transfer(id_, full body).
   To just enable/disable: switch_transfer(id_, body={"active": true|false}).
7. Verify: list_history(transfer_id) -> latest run id + status; get_history_status.
Output: which connectors were used, the created/updated transfer id + schedule, and the
first run's status. Echo the body before writing. Caveat: cluster_name must be supplied.

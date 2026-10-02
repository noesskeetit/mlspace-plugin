---
name: mlspace-launch-training-job
description: "Launch a training job on Cloud.ru MLSpace. Start/submit a training job (resolves instance type + base image). Write action. Uses the mlspace_jobs, mlspace_resources tools."
license: MIT
compatibility: Requires the `mlspace` MCP server from this plugin (Cloud.ru MLSpace credentials needed).
---

# Launch a training job

Start/submit a training job (resolves instance type + base image). Write action.

This skill drives the `mlspace` MCP server shipped in the same plugin. If its
tools are not connected, say so instead of guessing — none of these steps can be
carried out any other way.

## Arguments

- `script` **(required)** — Entrypoint: binary command/executable or NFS script path.
- `region` **(required)** — Target region; required for every job type.
- `gpus` — GPU count for the instance type; use 0 for CPU-only.
- `image_hint` — Base image keyword, e.g. pytorch.
- `job_type` — JobType; binary accepts a command/executable path.
- `n_workers` — Number of worker nodes.
- `queue_name` — Queue to schedule in.
- `extra_body` — JSON of extra RunJobRequest fields.
- `target` — Connected workspace ID or unambiguous name, if scoped.

## Procedure

Goal: submit a training job (jobs.run is a write action; refused if the server
runs with MLSPACE_READONLY=true).
PRECONDITION (critical, easy to miss): `region` must be explicit. Interpret `script`
according to `type`. For type=binary it is a non-empty command or executable path
(for example `ls -lah` or `python /home/jovyan/launch.py -f script.py`) and is forwarded
unchanged; do not force it under /home/jovyan. Verify that the command/executable exists
in the selected image. For other job types, `script` must already exist on that same
region's NFS under /home/jovyan (e.g. /home/jovyan/proj/train.py). `/home/jovyan` is
region-scoped: an SR006 notebook and an A100-MT job can see different contents at the
same path. The Public API has no remote stat operation, so the MCP cannot prove NFS
existence. If set, checkpoint_dir/logs_dir must use that same regional NFS.
1. Parse: script/command, explicit region from the actual MT catalogue,
   GPU count, image hint, job type (default
   binary; pytorch/torchrun/etc), n_workers. `gpus=0` means a CPU-only job.
2. mlspace_resources configs cluster_type=MT. Pick regions[].key == target region.
3. instance_type: among that region's instances_types[], pick by GPU count — for
   gpus>0 the one whose resource.limits['nvidia.com/gpu'] equals it; for gpus=0 a
   `cpu.*` type, where that limit is null or absent (it is a nullable STRING, so
   compare loosely). Use its `key`. Require a non-empty compatible `images` list;
   catalog presence alone does not prove PAYG/allocation eligibility.
4. base_image: filter the region's datahub_images/custom_images by the hint on .name;
   combine name + tag into the "name:tag" string. (Do NOT read instances_types[].images
   for this — the wrapper collapses those into pre-joined "name:tag1,tag2" reference
   strings; use them only to check WHICH images an instance type supports.)
5. (optional) queue_name/allocation_name are free-form strings; pass verbatim.
   max_retry is only supported inside allocations; omit it for PAYG jobs.
6. Build RunJobRequest: {script, base_image, instance_type, region, type, n_workers,
   plus any extra_body}. ECHO it and the relevant entrypoint evidence (binary command
   available in the image, or NFS script staged in that exact region) to the user for
   confirmation before submitting.
7. jobs run (body=...). Capture job_name.
8. Verify: jobs get (job_name) for initial status; jobs logs (tail=50) for first output.
Re-run shortcut: jobs restart (body={job_name}) to repeat an existing job.
Caveat: this spends compute. Confirm the resolved body with the user first. A valid
/home/jovyan prefix is necessary but not sufficient for NFS entrypoints: wrong-region
NFS fails fast and still burns startup capacity. Use the returned resource_ref for subsequent reads; report command/NFS availability
as unverified when no execution-environment evidence is available.

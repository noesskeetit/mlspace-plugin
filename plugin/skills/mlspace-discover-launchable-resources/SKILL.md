---
name: mlspace-discover-launchable-resources
description: "Discover what you can launch on Cloud.ru MLSpace. Valid instance types, base images and free GPUs in a region before launching. Uses the mlspace_allocations, mlspace_docker_registry, mlspace_queue_inspect, mlspace_resources, mlspace_workspaces tools."
license: MIT
compatibility: Requires the `mlspace` MCP server from this plugin (Cloud.ru MLSpace credentials needed).
---

# Discover what you can launch

Valid instance types, base images and free GPUs in a region before launching.

This skill drives the `mlspace` MCP server shipped in the same plugin. If its
tools are not connected, say so instead of guessing — none of these steps can be
carried out any other way.

## Arguments

- `region` — Target region.
- `cluster_type` — MT (jobs/notebooks) or INF (inference).
- `allocation_id` — Allocation id, if known; access varies by endpoint.
- `include_custom_images` — Also list registry images.
- `target` — Connected workspace ID or unambiguous name, if scoped.

## Procedure

Goal: list compatible instance types/images and observed capacity before launching.
1. mlspace_resources configs (cluster_type=MT for jobs/notebooks; INF for inference).
   Use the target region's actual instances_types keys, resource limits and
   datahub_images/custom_images. Include zero-GPU cpu.* types. An empty images list
   does not establish a compatible pairing; do not recommend an arbitrary image.
2. mlspace_resources nodes and mlspace_resources nodes_load for observable regional
   node/load facts. Available GPU readings are point-in-time and do not guarantee
   scheduling or idle nodes across workspaces. Missing readings remain unknown.
3. workspaces allocations in the selected target; if an allocation_id is available,
   allocations get/get_nodes/list_instance_types for additional observed facts.
   Report success/403/405/empty results per endpoint. Do not infer allocation access
   categorically from service-account vs personal credentials.
4. For a known queue, mlspace_queue_inspect(queue_id, target) examines candidate node
   facts, job/notebook/pod observations and pending priorities across selected observations.
   Keep paused notebooks visible; their configured GPUs are not active consumption.
   Do not sum shared views or claim complete cross-workspace coverage.
5. Optionally docker_registry current_registry -> list_repos -> list_tags for images.
Output: catalogue compatibility, observed capacity, actual scope/time and unresolved
eligibility or visibility. PAYG may reject a catalogue-valid type; read-only inspection
cannot promise a successful launch.

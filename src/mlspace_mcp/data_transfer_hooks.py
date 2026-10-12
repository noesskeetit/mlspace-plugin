"""Evidence boundaries alongside Data Transfer observations, without new API calls."""
from __future__ import annotations

from typing import Any

_DATA_IMPACT_GUIDANCE = (
    'In the final diagnosis explicitly state: Data impact is unverified. '
    'Do not claim that the source was read, nothing was written, or destination '
    'data is unchanged without an independent contents check. A failed PutObject '
    'describes that request, not other objects or earlier attempts in the run.'
)


def _unknown_evidence() -> dict[str, str]:
    return {
        'failure_cause': 'unknown',
        'failure_phase': 'unknown',
        'data_impact': 'unknown',
        'reporting_requirement': _DATA_IMPACT_GUIDANCE,
        'basis': 'Counters/empty logs alone; independent evidence may establish more.',
        'interpretation': (
            'Reported counters (including zero) and absent logs do not prove that '
            'the run stopped before reading/writing or left destination data unchanged.'
        ),
    }


def history_evidence(data: Any, values: dict[str, Any]) -> Any:
    """Preserve history shape and counters; failed/cancelled entries lack a diagnosis."""
    if isinstance(data, list):
        return [history_evidence(row, values) for row in data]
    if isinstance(data, dict):
        if isinstance(data.get('data'), list):
            return {**data, 'data': history_evidence(data['data'], values)}
        if data.get('status') in ('failed', 'cancelled'):
            return {**data, '_mcp_evidence': _unknown_evidence()}
    return data


def log_evidence(data: Any, values: dict[str, Any]) -> Any:
    """Keep log evidence intact; individual events are not a destination-data audit."""
    empty = data is None or data == [] or data == {} or data == ''
    recognized = isinstance(data, list)
    if isinstance(data, dict) and data:
        collections = {'items', 'data', 'events', 'logs'}
        metadata = {'count', 'total_count', 'offset', 'limit', 'page', 'page_size', 'status'}
        present = collections & data.keys()
        recognized = any(isinstance(data[key], list) for key in present)
        empty = bool(present) and all(data[key] == [] for key in present) and (
            not (data.keys() - collections - metadata)
        ) and all(not data.get(key) for key in ('count', 'total_count'))
    if empty:
        return {'result': data, '_mcp_evidence': _unknown_evidence()}
    if recognized:
        evidence = {
            'data_impact': 'unknown',
            'reporting_requirement': _DATA_IMPACT_GUIDANCE,
            'basis': 'Logs describe individual events, not a complete source/destination audit.',
            'interpretation': (
                'Use explicit log messages to identify cause and failure phase. '
                'Report data impact separately as unknown until source/destination contents '
                'are independently checked. Even AccessDenied and all-zero counters do not '
                'establish that this entire run left destination data unchanged.'
            ),
        }
        result = data if isinstance(data, dict) else {'result': data}
        return {**result, '_mcp_evidence': evidence}
    return data

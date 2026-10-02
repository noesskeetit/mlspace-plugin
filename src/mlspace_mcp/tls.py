"""One verified TLS policy for setup and runtime; no global SSL monkey patch."""
from __future__ import annotations

import os
import ssl

import httpx


def tls_context(ca_file: str = '') -> ssl.SSLContext:
    """Use OS trust and optionally an administrator-supplied PEM bundle."""
    extra = ca_file or os.environ.get('SSL_CERT_FILE', '')
    context: ssl.SSLContext
    try:
        import truststore
        context = truststore.SSLContext(ssl.PROTOCOL_TLS_CLIENT)
    except ImportError:
        context = ssl.create_default_context()
    if extra:
        context.load_verify_locations(cafile=extra)
    capath = os.environ.get('SSL_CERT_DIR')
    if capath:
        context.load_verify_locations(capath=capath)
    return context


def safe_error(exc: Exception) -> str:
    """Describe the cause without printing exception bodies or submitted values."""
    chain: list[BaseException] = []
    current: BaseException | None = exc
    while current is not None and all(current is not item for item in chain):
        chain.append(current)
        current = current.__cause__ or current.__context__
    if any(isinstance(item, ssl.SSLCertVerificationError) or
           (isinstance(item, (ssl.SSLError, httpx.ConnectError)) and
            'CERTIFICATE_VERIFY_FAILED' in str(item)) for item in chain):
        return ('TLS certificate verification failed. Use the corporate CA from your '
                'administrator: --ca-file /path/to/ca.pem. TLS verification remains enabled.')
    status = getattr(exc, 'status', None)
    if isinstance(status, int):
        return f'API request failed (HTTP {status}); check access keys and workspace permissions.'
    if any(isinstance(item, httpx.TimeoutException) for item in chain):
        return 'API request timed out; check network/VPN and retry.'
    if any(isinstance(item, httpx.ConnectError) for item in chain):
        return 'Could not connect; check network/VPN and the API endpoint.'
    return type(exc).__name__

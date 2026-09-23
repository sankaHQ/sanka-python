"""Guard the AnyIO hostname boundary fixed by CVE-2026-63374 without network I/O."""

import ssl
import unittest
from unittest.mock import patch

from anyio.streams.tls import TLSStream


class _HostnameCaptured(Exception):
    pass


class TlsDependencyTest(unittest.IsolatedAsyncioTestCase):
    async def test_tls_uses_idna2008_before_entering_openssl(self):
        for hostname, expected in (
            ("faß.example", b"xn--fa-hia.example"),
            ("straße.example", b"xn--strae-oqa.example"),
            ("api.example.com", b"api.example.com"),
        ):
            with self.subTest(hostname=hostname):
                captured = {}

                def capture_hostname(*args, **kwargs):
                    value = kwargs["server_hostname"]
                    # Mirror OpenSSL's IDNA 2003 fallback for unconverted strings.
                    captured["hostname"] = value.encode("idna") if isinstance(value, str) else value
                    raise _HostnameCaptured

                # Stop at OpenSSL's boundary: no socket, handshake or remote service.
                with patch.object(ssl.SSLContext, "wrap_bio", side_effect=capture_hostname):
                    with self.assertRaises(_HostnameCaptured):
                        await TLSStream.wrap(
                            object(), hostname=hostname, ssl_context=ssl.create_default_context()
                        )
                self.assertEqual(captured["hostname"], expected)

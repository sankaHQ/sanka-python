from __future__ import annotations

import unittest

import httpx

from sanka_sdk import SankaClient

WORKSPACE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
PNG = b"\x89PNG\r\n\x1a\n\x00\xff"


class PngResponse(httpx.Response):
    """A PNG response that fails the test if the SDK reads its body as text or JSON."""

    def json(self, **kwargs):
        raise AssertionError("the PNG body was parsed as JSON")

    @property
    def text(self):
        raise AssertionError("the PNG body was read as text")


class DiagramImageTransportTest(unittest.TestCase):
    def test_image_returns_the_raw_png_bytes_and_revision(self):
        requests = []

        def handler(request):
            requests.append(request)
            return PngResponse(200, content=PNG, headers={"content-type": "image/png", "x-sanka-diagram-revision": "7"})

        with httpx.Client(transport=httpx.MockTransport(handler)) as http:
            client = SankaClient(token="synthetic-token", httpx_client=http)
            image = b"".join(client.ferry_diagrams.get_public_ferry_diagram_image("diagram-1", workspace_id=WORKSPACE))
            with client.ferry_diagrams.with_raw_response.get_public_ferry_diagram_image("diagram-1") as response:
                revision = response.headers["x-sanka-diagram-revision"]
                raw_image = b"".join(response.data)

        self.assertEqual(image, PNG)
        self.assertEqual((raw_image, revision), (PNG, "7"))
        request = requests[0]
        self.assertEqual((request.method, request.url.path), ("GET", "/v2/public/ferry/diagrams/diagram-1/image"))
        self.assertEqual(request.url.params["workspace_id"], WORKSPACE)
        self.assertEqual(request.headers["Authorization"], "Bearer synthetic-token")


if __name__ == "__main__":
    unittest.main()

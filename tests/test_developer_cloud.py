from __future__ import annotations

import asyncio
import json
import unittest

import httpx

from sanka_sdk import AsyncSankaClient, SankaClient

WORKSPACE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
RUN = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"


class DeveloperCloudTransportTest(unittest.TestCase):
    def setUp(self):
        self.requests = []

        def handler(request):
            self.requests.append(request)
            return httpx.Response(409, json={"success": False, "error": {"code": "FIXTURE_CONFLICT"}})

        self.client = SankaClient(
            token="synthetic-token", httpx_client=httpx.Client(transport=httpx.MockTransport(handler))
        )

    def test_create_preserves_approved_cap_and_key(self):
        with self.assertRaises(Exception) as caught:
            self.client.developer_cloud.create_run(
                workspace_id=WORKSPACE,
                idempotency_key="approved-sdk-001",
                source_id=RUN,
                source_sha_256="a" * 64,
                max_credits=100,
                timeout_seconds=60,
            )
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(len(self.requests), 1)
        request = self.requests[0]
        self.assertEqual(str(request.url).split("?")[0], "https://api.sanka.com/v2/migrate/cloud-runs")
        self.assertEqual(request.url.params["workspace_id"], WORKSPACE)
        self.assertEqual(request.headers["Authorization"], "Bearer synthetic-token")
        self.assertEqual(request.headers["Idempotency-Key"], "approved-sdk-001")
        self.assertEqual(
            json.loads(request.content),
            {
                "source_id": RUN,
                "source_sha256": "a" * 64,
                "max_credits": 100,
                "timeout_seconds": 60,
            },
        )

    def test_retry_preserves_selected_children_and_new_budget(self):
        with self.assertRaises(Exception):
            self.client.developer_cloud.retry_fleet(
                RUN,
                workspace_id=WORKSPACE,
                idempotency_key="approved-retry-001",
                item_keys=["failed-three"],
                max_credits=100,
                concurrency=1,
            )
        request = self.requests[0]
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(request.url.path, f"/v2/migrate/cloud-fleets/{RUN}/retry")
        self.assertEqual(request.url.params["workspace_id"], WORKSPACE)
        self.assertEqual(
            json.loads(request.content), {"item_keys": ["failed-three"], "max_credits": 100, "concurrency": 1}
        )

    def test_binary_download_preserves_bytes(self):
        content = b"PK\x03\x04\xff\x00"

        def handler(request):
            self.requests.append(request)
            return httpx.Response(200, content=content, headers={"content-type": "application/octet-stream"})

        client = SankaClient(token="synthetic-token", httpx_client=httpx.Client(transport=httpx.MockTransport(handler)))
        self.assertEqual(
            b"".join(client.developer_cloud.get_artifact(RUN, "output.zip", workspace_id=WORKSPACE)), content
        )
        self.assertEqual(self.requests[0].url.params["workspace_id"], WORKSPACE)

    def test_certificate_revocation_keeps_reason_and_run(self):
        with self.assertRaises(Exception):
            self.client.developer_cloud.revoke_certificate(RUN, workspace_id=WORKSPACE, reason="Candidate withdrawn")
        self.assertEqual(self.requests[0].url.path, f"/v2/migrate/cloud-runs/{RUN}/certificate/revoke")
        self.assertEqual(json.loads(self.requests[0].content), {"reason": "Candidate withdrawn"})

    def test_async_availability_flags_are_preserved(self):
        async def check():
            def handler(request):
                self.requests.append(request)
                return httpx.Response(
                    200,
                    json={
                        "success": True,
                        "data": {
                            "enabled": False,
                            "repair_enabled": False,
                            "certification_enabled": False,
                            "fleet_enabled": False,
                        },
                        "meta": {"ctx_id": "synthetic-sdk-test"},
                    },
                )

            client = AsyncSankaClient(
                token="synthetic-token", httpx_client=httpx.AsyncClient(transport=httpx.MockTransport(handler))
            )
            result = await client.developer_cloud.get_availability(workspace_id=WORKSPACE)
            self.assertFalse(result.data.enabled)
            self.assertFalse(result.data.fleet_enabled)
            self.assertEqual(self.requests[0].url.params["workspace_id"], WORKSPACE)

        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()

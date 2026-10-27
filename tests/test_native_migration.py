"""Generated native methods preserve scoped recovery/content-read HTTP contracts."""

import asyncio
import json
import unittest

import httpx

from sanka_sdk import AsyncSankaClient, SankaClient

WORKSPACE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
RUN = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
HASH = "sha256:" + "a" * 64


class NativeMigrationTransportTest(unittest.TestCase):
    def test_native_preparation_and_recovery_keep_confirmations_and_keys(self):
        calls = []

        def handler(request):
            calls.append(request)
            return httpx.Response(409, json={"success": False, "error": {"code": "MIGRATION_NATIVE_CONFLICT"}})

        client = SankaClient(token="synthetic", httpx_client=httpx.Client(transport=httpx.MockTransport(handler)))
        cases = [
            (
                client.sanka_migrate.prepare_native_migration_api,
                "native-prepare",
                {
                    "expected_binding_hash": HASH,
                    "expected_revision": 2,
                    "expected_review_hash": HASH,
                },
                {"confirm_source_content_read": True},
            ),
            (
                client.sanka_migrate.recover_native_migration_api,
                "native-recovery",
                {
                    "expected_binding_hash": HASH,
                    "operation_id": "thread_message:opaque",
                    "expected_operation_revision": "2026-10-27T00:00:00+00:00",
                    "destination_id": "19:opaque@thread.v2",
                    "evidence": "Reviewed provider correspondence",
                },
                {"confirm": True},
            ),
            (
                client.sanka_migrate.recover_native_migration_api,
                "native-recovery",
                {
                    "expected_binding_hash": HASH,
                    "operation_id": "sharepoint_package:opaque",
                    "expected_operation_revision": "2026-10-27T00:00:00+00:00",
                    "action": "resume_staging",
                    "evidence": "No submission was dispatched",
                },
                {"confirm": True},
            ),
        ]
        for method, path, body, constants in cases:
            with self.subTest(path=path, action=body.get("action")):
                before = len(calls)
                with self.assertRaises(Exception):
                    method(RUN, workspace_id=WORKSPACE, idempotency_key="native-approved-key", **body)
                self.assertEqual(len(calls), before + 1)
                request = calls[-1]
                self.assertEqual(request.method, "POST")
                self.assertEqual(request.url.path, f"/v2/migrate/migrations/{RUN}/{path}")
                self.assertEqual(request.url.params["workspace_id"], WORKSPACE)
                self.assertEqual(request.headers["Authorization"], "Bearer synthetic")
                self.assertEqual(request.headers["Idempotency-Key"], "native-approved-key")
                self.assertEqual(json.loads(request.content), {**body, **constants})

    def test_async_review_deserializes_opaque_operation_receipt(self):
        async def check():
            calls = []

            def handler(request):
                calls.append(request)
                return httpx.Response(
                    200,
                    json={
                        "success": True,
                        "data": {
                            "mode": "native",
                            "binding_hash": HASH,
                            "status": "prepared",
                            "operations": [
                                {
                                    "id": "thread_message:opaque",
                                    "state": "uncertain",
                                    "destinationId": "19:opaque@thread.v2",
                                }
                            ],
                        },
                        "meta": {"ctx_id": "native-sdk-test"},
                    },
                )

            async with httpx.AsyncClient(transport=httpx.MockTransport(handler)) as http:
                client = AsyncSankaClient(token="synthetic", httpx_client=http)
                response = await client.sanka_migrate.get_native_review_api(RUN, workspace_id=WORKSPACE)
            self.assertEqual(response.data.operations[0]["destinationId"], "19:opaque@thread.v2")
            self.assertEqual(calls[0].url.path, f"/v2/migrate/migrations/{RUN}/native-review")
            self.assertEqual(calls[0].url.params["workspace_id"], WORKSPACE)

        asyncio.run(check())

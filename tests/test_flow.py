from __future__ import annotations

import asyncio
import json
import unittest

import httpx

from sanka_sdk import AsyncSankaClient, SankaClient

WORKSPACE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
REQUEST = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
WORKFLOW = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
DIGEST = "sha256:" + "a" * 64


def envelope(data):
    return {"success": True, "data": data, "meta": {"ctx_id": "flow-sdk-test"}}


class FlowTransportTest(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.data = {}
        self.status = 200

        def handler(request):
            self.requests.append(request)
            return httpx.Response(self.status, json=self.data)

        self.transport = httpx.MockTransport(handler)
        self.http = httpx.Client(transport=self.transport)
        self.client = SankaClient(token="synthetic-token", httpx_client=self.http)

    def tearDown(self):
        self.http.close()

    def test_plan_preserves_request_workspace_and_scalars(self):
        parameters = {"invoice_due_days": 45, "interval_minutes": 90, "deal_stage_ids": ["closedwon"]}
        self.data = envelope(
            {
                "workspace_id": WORKSPACE,
                "request_id": REQUEST,
                "plan_digest": DIGEST,
                "template_id": "billing.hubspot-deal-invoices",
                "template_version": 1,
                "operation": "create",
                "applicable": True,
                "parameters": parameters,
                "construction": "inactive",
            }
        )
        result = self.client.workflows.plan_public_workflow_template_api(
            workspace_id=WORKSPACE,
            request_id=REQUEST,
            template_id="billing.hubspot-deal-invoices",
            template_version=1,
            parameters=parameters,
        )
        self.assertEqual(result.data.plan_digest, DIGEST)
        self.assertEqual(result.data.parameters, parameters)
        request = self.requests[0]
        self.assertEqual(request.url.path, "/v2/public/workflows/templates/plan")
        self.assertEqual(request.url.params["workspace_id"], WORKSPACE)
        self.assertEqual(request.headers["Authorization"], "Bearer synthetic-token")
        self.assertEqual(
            json.loads(request.content),
            {
                "request_id": REQUEST,
                "template_id": "billing.hubspot-deal-invoices",
                "template_version": 1,
                "parameters": parameters,
            },
        )

    def test_use_returns_original_committed_receipt_without_activation(self):
        self.data = envelope(
            {
                "workspace_id": WORKSPACE,
                "workflow_id": WORKFLOW,
                "request_id": REQUEST,
                "plan_digest": DIGEST,
                "definition_digest": DIGEST,
                "status": "already_constructed",
            }
        )
        result = self.client.workflows.use_public_workflow_template_api(
            workspace_id=WORKSPACE,
            request_id=REQUEST,
            plan_digest=DIGEST,
        )
        self.assertEqual(result.data.workflow_id, WORKFLOW)
        self.assertEqual(result.data.status, "already_constructed")
        self.assertEqual(len(self.requests), 1)
        self.assertEqual(json.loads(self.requests[0].content), {"request_id": REQUEST, "plan_digest": DIGEST})

    def test_stale_construct_does_not_resubmit(self):
        self.status = 409
        self.data = {"success": False, "error": {"code": "WORKFLOW_FLOW_CONFLICT", "message": "Review again"}}
        with self.assertRaises(Exception) as caught:
            self.client.workflows.construct_public_workflow_flow_api(
                WORKFLOW,
                workspace_id=WORKSPACE,
                plan_digest=DIGEST,
                attempt_id=REQUEST,
            )
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(len(self.requests), 1)
        request = self.requests[0]
        self.assertEqual(request.url.path, f"/v2/public/workflows/{WORKFLOW}/flow/construct")
        self.assertEqual(json.loads(request.content), {"plan_digest": DIGEST, "attempt_id": REQUEST})

    def test_async_status_preserves_current_and_baseline_settings(self):
        self.data = envelope(
            {
                "workspace_id": WORKSPACE,
                "workflow_id": WORKFLOW,
                "status": "managed",
                "definition_digest": DIGEST,
                "active": False,
                "parameters": {"invoice_due_days": 45},
                "template_parameters": {"invoice_due_days": 30},
                "available_operations": ["plan", "construct"],
            }
        )

        async def check():
            async with httpx.AsyncClient(transport=self.transport) as http:
                client = AsyncSankaClient(token="synthetic-token", httpx_client=http)
                result = await client.workflows.get_public_workflow_flow_api(WORKFLOW, workspace_id=WORKSPACE)
                self.assertEqual(result.data.parameters["invoice_due_days"], 45)
                self.assertEqual(result.data.template_parameters["invoice_due_days"], 30)
                self.assertEqual(result.data.available_operations, ["plan", "construct"])

        asyncio.run(check())


if __name__ == "__main__":
    unittest.main()

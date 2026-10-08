from __future__ import annotations

import asyncio
import json
import unittest

import httpx

from sanka_sdk import AsyncSankaClient, SankaClient
from sanka_sdk.types.presentation_patch_request_ops_item import (
    PresentationPatchRequestOpsItem_DeleteSlides,
    PresentationPatchRequestOpsItem_InsertBlocks,
    PresentationPatchRequestOpsItem_SetTitle,
)

WORKSPACE = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
PRESENTATION = "bbbbbbbb-bbbb-4bbb-8bbb-bbbbbbbbbbbb"
PROGRAM = "cccccccc-cccc-4ccc-8ccc-cccccccccccc"
EXPORT = "dddddddd-dddd-4ddd-8ddd-dddddddddddd"
DECK = {
    "schema": "sanka.deck/v1",
    "page": {"size": "16:9"},
    "theme": {"id": "sanka-paper"},
    "slides": [
        {
            "id": "s1",
            "blocks": [
                {"type": "heading", "id": "h1", "level": 1, "text": "Q4 review"},
                {"type": "text", "id": "t1", "markdown": "- Revenue up"},
            ],
        }
    ],
}


def envelope(data):
    return {"success": True, "data": data, "meta": {"ctx_id": "presentations-sdk-test"}}


def presentation(revision=3):
    return {
        "id": PRESENTATION,
        "workspaceId": WORKSPACE,
        "product": "flow",
        "kind": "presentation",
        "title": "Q4 review",
        "revision": revision,
        "deck": DECK,
        "slideCount": 1,
        "outline": "# Q4 review",
        "updatedVia": "api",
        "appPath": f"/docs?presentation={PRESENTATION}",
    }


class PresentationsTransportTest(unittest.TestCase):
    def setUp(self):
        self.requests = []
        self.response = httpx.Response(200, json={})

        def handler(request):
            self.requests.append(request)
            return self.response

        self.transport = httpx.MockTransport(handler)
        self.http = httpx.Client(transport=self.transport)
        self.client = SankaClient(token="synthetic-token", httpx_client=self.http)

    def tearDown(self):
        self.http.close()

    def test_create_sends_the_deck_unchanged_and_parses_typed_blocks(self):
        self.response = httpx.Response(201, json=envelope(presentation(revision=1)))
        result = self.client.presentations.create_public_presentation(
            workspace_id=WORKSPACE, title="Q4 review", deck=DECK, source_ref="crm:q4"
        )
        heading, text = result.data.deck.slides[0].blocks
        self.assertEqual((heading.type, heading.text), ("heading", "Q4 review"))
        self.assertEqual(text.markdown, "- Revenue up")
        request = self.requests[0]
        self.assertEqual((request.method, request.url.path), ("POST", "/v2/public/documents/presentations"))
        self.assertEqual(request.url.params["workspace_id"], WORKSPACE)
        self.assertEqual(request.headers["Authorization"], "Bearer synthetic-token")
        self.assertEqual(json.loads(request.content), {"title": "Q4 review", "deck": DECK, "sourceRef": "crm:q4"})

    def test_update_sends_discriminated_edit_ops_at_the_expected_revision(self):
        self.response = httpx.Response(200, json=envelope(presentation(revision=4)))
        result = self.client.presentations.update_public_presentation(
            PRESENTATION,
            workspace_id=WORKSPACE,
            expected_revision=3,
            ops=[
                PresentationPatchRequestOpsItem_SetTitle(title="Q4 board review"),
                PresentationPatchRequestOpsItem_InsertBlocks(
                    slide_id="s1", after="h1", blocks=[{"type": "callout", "markdown": "Ship it"}]
                ),
                PresentationPatchRequestOpsItem_DeleteSlides(slide_ids=["s9"]),
            ],
        )
        self.assertEqual(result.data.revision, 4)
        request = self.requests[0]
        self.assertEqual(
            (request.method, request.url.path), ("PATCH", f"/v2/public/documents/presentations/{PRESENTATION}")
        )
        self.assertEqual(
            json.loads(request.content),
            {
                "expectedRevision": 3,
                "ops": [
                    {"op": "set_title", "title": "Q4 board review"},
                    {
                        "op": "insert_blocks",
                        "slideId": "s1",
                        "after": "h1",
                        "blocks": [{"type": "callout", "markdown": "Ship it"}],
                    },
                    {"op": "delete_slides", "slideIds": ["s9"]},
                ],
            },
        )

    def test_stale_replace_fails_once_with_the_revision_conflict(self):
        conflict = {"code": "PRESENTATION_REVISION_CONFLICT", "message": "Revision 4 is current"}
        self.response = httpx.Response(409, json={"success": False, "error": conflict})
        with self.assertRaises(Exception) as caught:
            self.client.presentations.replace_public_presentation(PRESENTATION, expected_revision=3, deck=DECK)
        self.assertEqual(caught.exception.status_code, 409)
        self.assertEqual(caught.exception.body["error"], conflict)
        self.assertEqual([request.method for request in self.requests], ["PUT"])

    def test_upload_image_sends_a_multipart_file_part(self):
        image = {
            "assetId": "asset-1",
            "contentType": "image/png",
            "sizeBytes": 4,
            "width": 1,
            "height": 1,
            "alt": "Logo",
        }
        self.response = httpx.Response(201, json=envelope(image))
        result = self.client.presentations.upload_public_presentation_image(
            PRESENTATION, file=("logo.png", b"\x89PNG", "image/png"), alt="Logo"
        )
        self.assertEqual(result.data.asset_id, "asset-1")
        request = self.requests[0]
        self.assertEqual(request.url.path, f"/v2/public/documents/presentations/{PRESENTATION}/images")
        self.assertTrue(request.headers["content-type"].startswith("multipart/form-data"))
        body = request.read()
        self.assertIn(b'name="file"; filename="logo.png"\r\nContent-Type: image/png\r\n\r\n\x89PNG\r\n', body)
        self.assertIn(b'name="alt"\r\n\r\nLogo\r\n', body)

    def test_program_export_uses_the_program_route_and_idempotency_key(self):
        queued = {
            "id": EXPORT,
            "documentId": PRESENTATION,
            "product": "sanka",
            "revision": 3,
            "format": "pdf",
            "status": "queued",
        }
        self.response = httpx.Response(202, json=envelope(queued))
        result = self.client.presentations.create_public_program_presentation_export(
            PROGRAM, PRESENTATION, workspace_id=WORKSPACE, idempotency_key="q4-pdf", format="pdf", include_notes=False
        )
        self.assertEqual(result.data.status, "queued")
        request = self.requests[0]
        self.assertEqual(request.url.path, f"/v2/public/ferry/programs/{PROGRAM}/presentations/{PRESENTATION}/exports")
        self.assertEqual(request.headers["Idempotency-Key"], "q4-pdf")
        self.assertEqual(json.loads(request.content), {"format": "pdf", "includeNotes": False})

    def test_async_download_preserves_the_raw_file_bytes(self):
        payload = b"%PDF-\xff\x00"
        self.response = httpx.Response(200, content=payload, headers={"content-type": "application/pdf"})

        async def check():
            async with httpx.AsyncClient(transport=self.transport) as http:
                client = AsyncSankaClient(token="synthetic-token", httpx_client=http)
                chunks = client.presentations.download_public_program_presentation_export(
                    PROGRAM, PRESENTATION, EXPORT, workspace_id=WORKSPACE
                )
                return b"".join([chunk async for chunk in chunks])

        self.assertEqual(asyncio.run(check()), payload)
        self.assertEqual(
            self.requests[0].url.path,
            f"/v2/public/ferry/programs/{PROGRAM}/presentations/{PRESENTATION}/exports/{EXPORT}/download",
        )


if __name__ == "__main__":
    unittest.main()

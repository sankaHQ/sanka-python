import unittest

import httpx

import sanka_sdk


class TopLevelErrorsTest(unittest.TestCase):
    def test_a_rejected_key_is_caught_by_the_top_level_error_classes(self):
        def handler(request: httpx.Request) -> httpx.Response:
            return httpx.Response(
                401,
                json={
                    "success": False,
                    "error": {"code": "INVALID_AUTHENTICATION", "message": "Invalid token"},
                    "meta": {"ctx_id": "errors-test"},
                },
            )

        client = sanka_sdk.SankaClient(
            token="synthetic-token", httpx_client=httpx.Client(transport=httpx.MockTransport(handler))
        )
        with self.assertRaises(sanka_sdk.UnauthorizedError) as caught:
            client.public_auth.get_public_auth_whoami_api()

        self.assertIsInstance(caught.exception, sanka_sdk.ApiError)
        self.assertEqual(caught.exception.status_code, 401)
        self.assertIsInstance(caught.exception.body, sanka_sdk.ErrorEnvelope)


if __name__ == "__main__":
    unittest.main()

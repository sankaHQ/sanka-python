# Developer Cloud release candidate

This SDK adds the V2 Developer Cloud contract. SDK installation alone does not
enable paid execution. Check availability in the intended workspace before
starting a run. Free local migration continues through `sanka_sdk.migrate`.

```python
import os
from sanka_sdk import SankaClient

client = SankaClient(token=os.environ["SANKA_API_TOKEN"])
workspace_id = "YOUR_INTERNAL_WORKSPACE_UUID"
availability = client.developer_cloud.get_availability(workspace_id=workspace_id)
print(availability.data)
```

`enabled`, `repair_enabled`, `certification_enabled` and `fleet_enabled` report
current admission. Existing history and receipts remain readable while disabled.
API tokens need the matching `migrate:cloud:read` or `migrate:cloud:write` scope.

Upload an explicitly approved ZIP snapshot with `upload_source`. Pass its base64
bytes as `archive_base64`, `sha256`, and optional full `revision`; the ZIP limit is 8 MiB.
The revision is a caller-declared claim. Its digest pins the actual uploaded bytes;
it does not independently prove Git provenance. Source upload is free and starts
no worker. Exclude credentials and use the returned source ID and SHA-256.

After the user has approved this exact source and cap:

```python
response = client.developer_cloud.create_run(
    workspace_id=workspace_id,
    idempotency_key="YOUR_STABLE_APPROVED_INTENT_KEY",
    source_id="UPLOADED_SOURCE_UUID",
    source_sha_256="UPLOADED_SOURCE_SHA256",
    max_credits=100,
    timeout_seconds=60,
)
print(response.data.id, response.data.status)
```

Keep the key and exact request after a lost response. Replaying that intent returns
the same run; changing its source or cap conflicts. Do not automatically increase
the cap or replace the key. Read persisted terminal state and the final receipt
before reporting completion. Cancellation is a request; poll until it settles.

| Workflow | `client.developer_cloud` methods |
| --- | --- |
| Run | `create_run`, `list_runs`, `get_run`, `cancel_run` |
| Evidence | `list_events`, `get_receipt`, `list_artifacts`, `get_artifact` |
| Certificate | `list_certificate_keys`, `get_certificate`, `revoke_certificate` |
| Fleet | `create_fleet`, `list_fleets`, `get_fleet`, `cancel_fleet`, `retry_fleet` |

Repair uses `create_run(repair=...)` with a pinned parent/candidate, failing gate
and allowed paths. Certification uses `certification=...` and
`verification_profile="independent-http-replay-v1"`. Read the generated request
models for the complete profile. An issued certificate covers only the recorded
scenarios and limitations. Verify its signature offline using the CLI and public
key, and read revocation status before relying on it.

Compute is 100 credits per active worker-minute, rounded once per run. A successful
Repair adds 1,000 credits and durable certificate issuance adds 2,000; both also
use compute. Failed gates earn no premium. The entire compute/premium reservation
fits within `max_credits`; unused credits are released. Re-reading evidence is free.

A Fleet contains 1–20 explicitly selected repository labels, full revisions and
child requests. Its cap equals the sum of child caps, reserved atomically. Set
concurrency from 1 to 5; the workspace-wide active-worker limit remains five.
Fleet adds no surcharge. A partial result remains partial. After settlement,
`retry_fleet` creates a new Fleet for the selected failed keys with a newly approved
cap equal to their original caps; successful children retain their old receipts.

`get_artifact` returns an iterator of bytes for binary output. Compare downloaded size and
SHA-256 with `list_artifacts` before using the contents. Source, logs and output are
retained for seven days; receipts and certificate metadata retain their identities.
No SDK method creates a repository PR, merges, deploys or purchases credits.

The asynchronous client is `AsyncSankaClient` with the same methods. Supply
`workspace_id` on every call. The generated Python name `source_sha_256` serializes
to the exact API field `source_sha256`.

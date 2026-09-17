# TSO callback ingress body limit

The TSO production example values set this per-Ingress limit without modifying
the chart defaults:

```yaml
ingress:
  main:
    annotations:
      nginx.ingress.kubernetes.io/proxy-body-size: "16m"
```

This covers `/submit-attestation-signatures` and the other routes served by
the TSO Ingress. It does not require changing the ingress controller's global
ConfigMap. The September 2026 testnet incident involved valid signed callbacks
of approximately 3,486,000 bytes that nginx rejected at its effective `1m`
limit before they reached TSO. The deployed `v0.3.0-beta.3g` application's
PSBT-carrying routes had a `4 * 1024 * 1024` byte HTTP body ceiling.

## Three separate limits

| Limit | What it measures | How to configure it |
| --- | --- | --- |
| PSBT field | The Base64-encoded PSBT string, not the decoded binary transaction | Applicable PSBT limits in the deployed TSO and signer release |
| Application HTTP body | The complete serialized JSON callback, including the PSBT and all other fields | The body limit implemented by the deployed TSO release |
| Ingress HTTP body | The complete incoming HTTP request body before forwarding to TSO | `nginx.ingress.kubernetes.io/proxy-body-size` on the TSO Ingress |

`16m` is 16 MiB (16,777,216 bytes). It deliberately leaves ingress headroom
above the observed 4 MiB TSO application-body ceiling, including the JSON and
Base64 overhead around a PSBT, so nginx is not the first component to reject a
valid application-sized callback. Increasing only a PSBT environment variable
does not increase either HTTP body limit. Conversely, raising the ingress
limit cannot bypass TSO's application limit. Check the actual image release
and measure the serialized callback when tuning these limits.

## Overrides and deployment

Use `examples/values/tso-service-production.yaml` as the production starting
point and fill its host and image before installation. The example sets `16m`
for nginx while leaving the packaged chart defaults unchanged.

Keep certificate-manager and access-control annotations in the same map. To
override the limit deliberately, put the desired string value in your
deployment values, or apply an operator overlay **after** the production file:

```yaml
ingress:
  main:
    annotations:
      cert-manager.io/cluster-issuer: my-issuer
      nginx.ingress.kubernetes.io/proxy-body-size: "32m"
```

The example `32m` only changes nginx; it does not raise TSO's 4 MiB ceiling.
For another ingress controller, configure its equivalent limit and set the
nginx annotation to YAML `null` to remove the value supplied by the production
example.

Deploy using the existing chart version and the reviewed example values. If an
existing release uses `--reuse-values`, pass the updated example values
explicitly; the unchanged chart defaults do not add the annotation. Review the
rendered Ingress and the live annotation after applying the values. Explicit
overrides, including a smaller `1m`, remain operator-owned.

## Public ingress integration check

Run this check in a test deployment with a fresh, pending TSO transaction and
a valid signed callback from an authorized attestation signer. Use a callback
larger than 1 MiB and smaller than 4 MiB (the incident-sized fixture is about
3.49 MB). Its transaction, signer identity, signatures, and policy context
must match that deployment. Do not use an old terminal transaction or padded
dummy JSON as an acceptance fixture.

1. Set the test deployment identifiers and inspect the live Ingress:

   ```sh
   namespace=default
   tso_host=tso.test.example.com
   kubectl -n "$namespace" get ingress tso-service -o yaml
   ```

   Verify the host, callback path/backend, ingress class, and explicit `16m`
   annotation. Then inspect `nginx -T` in the controller Pod serving that
   Ingress. Locate the `server_name` for this host and the callback's matching
   location; verify its effective `client_max_body_size 16m`. An annotation
   alone does not prove the controller has reloaded it.

2. Save the valid callback's complete JSON as `callback.json`. Confirm its
   exact wire size without reserializing or modifying signed data:

   ```sh
   python - <<'PY'
   import json
   from pathlib import Path
   body = Path("callback.json").read_bytes()
   json.loads(body)
   assert 1024 * 1024 < len(body) < 4 * 1024 * 1024, len(body)
   print(f"Callback body: {len(body)} bytes")
   PY
   ```

3. Submit once through the public HTTPS host, with the deployment's required
   authentication if applicable. Coordinate with the signer so this fixture
   has not already been submitted. This operation advances a real test
   transaction:

   ```sh
   curl --silent --show-error --fail-with-body \
     --header 'Content-Type: application/json' \
     --data-binary @callback.json \
     --dump-header callback-response.headers \
     --output callback-response.json \
     "https://${tso_host}/submit-attestation-signatures"
   cat callback-response.headers callback-response.json
   ```

4. Require a successful application response and correlate the transaction ID
   and signer with TSO logs/state: the signature must be accepted and counted
   toward attestation quorum. Check the ingress access log for the same
   request and upstream result. Preserve the body byte count, response status,
   transaction ID, controller configuration excerpt, and quorum evidence.
   A `400`/`404`, absence of nginx `413`, duplicate acknowledgment, or an
   internal Service-only request does not satisfy this acceptance check.

## Terminal requests are a separate recovery concern

Correcting the Ingress does not reopen signer requests that exhausted callback
retries or WP actions already marked `failed_terminal`. In the reported
incident, a later normal AdvanceL2 moved the WF head and created a different
AdvanceL1 transaction, which succeeded after the ingress correction. The old
records remained terminal. Keep any terminal-execution recovery procedure
separate from this deployment change; this fix performs no database resets,
manual signature callbacks, or confirmations changes.

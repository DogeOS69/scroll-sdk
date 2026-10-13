# Attestation key rotation (devops)

A rotation replaces the bridge's attestation signer set. Devops runs the three
`scrollsdk bridge rotation` commands; signers follow the
[signer kit README](../partner-kit/attestation-signer/README.md).

## 0. Deployment kit (once per deployment, not per rotation)

```bash
scrollsdk setup export-deployment-kit --kit-version 1
```

Publish the kit directory unchanged at an immutable URL and record its manifest
SHA-256 on the deployment's Governance record. A rotation does not need a new kit.

## 1. New signers

Each new signer, in a fresh copy of the signer kit:

```bash
./signer.sh init --name <name> --network mainnet [--backend aws-kms ...]
./signer.sh import <kit-dir> <manifest-sha256-from-the-Governance-record>
./signer.sh start
```

They add `identity.json` to the Governance portal. Until devops registers them,
the TSO refuses their polls and `/health` shows `tso: auth_rejected`; that is expected.

## 2. Export

In the portal, create the rotation proposal and use **Download rotation export**
(`rotation-export.json`). Export when the old signers are ready to approve and
you are ready to register. If more than about a week passes before `send`, re-export.

## 3. Old signers approve, one at a time

Each current signer runs `./signer.sh inspect rotation-export.json`, adds the
printed `allowed_next_bridge_script_hashes` line under `[rotation_policy]` in
`attestation-signer.toml`, then runs `./signer.sh start` and `./signer.sh check`.
Restart one signer at a time so at least M stay up.

## 4. Register, check, send

```bash
scrollsdk bridge rotation register rotation-export.json --dir ./deployment
scrollsdk bridge rotation online   rotation-export.json --dir ./deployment
scrollsdk bridge rotation send     rotation-export.json --dir ./deployment --preview
scrollsdk bridge rotation send     rotation-export.json --dir ./deployment
```

- `register` checks the export against the live WP, adds every current and target
  signer to the WP `tsoSigners`, and upgrades the WP. It never removes entries.
- `online` passes when every target key and at least M current keys polled the TSO in the last 60 s.
- `send --preview` runs every check and builds the transaction; it stores nothing.
- `send` submits once. On any HTTP error the intent may already be stored: re-run
  `send`, which then only reports the stored intent and never resubmits.

## 5. Verify

Re-run `send`; it prints the intent state (`completed` when done). Then read the WP status:

```bash
kubectl port-forward pod/withdrawal-processor-0 3000 &
curl -s localhost:3000/protocol-actions/rotate-key/status | jq '{current_key_hash, deprecating, next_wf_tx_number}'
```

`current_key_hash` must be the export's `target.key_hash`. Confirm in the new
signers' logs that they sign the next withdrawal flow.

## 6. Retire

- **Old signers** may stop, and remove their allowlist line, once
  `next_wf_tx_number >= deprecating.deprecation_wf_tx_number`. Keep at least M up until then.
- **Devops** removes the old keys from `tsoSigners` (a manual values edit, then
  `make install-withdrawal-processor`) only after the status shows `deprecating = null`.
  Pruning earlier stops the WP from starting. Keep any key another live script still uses.

## Limits

- There is no cancel after `send`. Use the checks and `--preview` first.
- `online` proves an authenticated TSO poll, not that a signer can sign: not its
  release, enforce mode, RPC health or that it loaded the allowlist line.

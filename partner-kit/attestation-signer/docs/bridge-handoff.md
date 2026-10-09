# Bridge operator handoff

These commands run in the **bridge deployment workspace**, not on the partner
host. For a new bridge, first collect one descriptor per signer and import the
complete approved set. This command selects bootstrap inputs; it is not an
on-chain key-rotation operation:

```bash
scrollsdk setup attestation-signer \
  --descriptor-dir descriptors/ \
  --active-signer-ids partner-a,partner-b,operator-a \
  --threshold 2
```

Use the actual signer IDs and threshold. The command updates the external
signer directory in `doge-config.toml` and the initial keyset in
`setup_defaults.toml`; it does not deploy or probe partner hosts.

Follow the CLI [setup order](https://github.com/DogeOS69/scroll-sdk-cli/blob/feat/signer-edge-buckets/docs/setup-order.md)
and [proof operator runbook](https://github.com/DogeOS69/scroll-sdk-cli/blob/feat/signer-edge-buckets/docs/proof-operator-runbook.md):

1. For a new bridge only, complete its service/key prerequisites and
   `scrollsdk setup bridge-init` to produce `.data/protocol_context.json`.
   An existing bridge keeps its canonical context and follows its upgrade
   procedure; do not reinitialize it to refresh a signer bundle.
2. Prepare the matching proof materials and select the proof intent, including
   mode, generation, and enforcement. Real materials bind the canonical context,
   approved program commitments, aggregate verifying key, and compiler inputs.
3. Run `scrollsdk setup prep-charts` to select the deployment contract. When
   selecting a real materials receipt explicitly, use
   `--proof-materials-receipt <reviewed-receipt-path>`.
4. Export into a **new** directory; the exporter refuses an existing output.
   It validates the selected contract and bound material hashes. After changes
   to proof intent/materials, rerun `prep-charts` before exporting.

```bash
scrollsdk setup export-signer-policy \
  --out signer-policy-bundle-beta6-001 \
  --tso-url https://tso.bridge.example
scrollsdk setup proof-config-check
sha256sum signer-policy-bundle-beta6-001/signer-policy-manifest.json
```

Replace the example TSO hostname with the reviewed public endpoint. The TSO
Ingress exposes `/health` and signed `/signer/*`, on an ALB separate from the
proof coordinator. The proof artifact GET base is the compiler-selected proof
store, not the DA archive bucket. Confirm these endpoints and any ingress/network
policies are ready for partner traffic.

Send the entire versioned directory and communicate its manifest SHA-256 through
the agreed handoff channel. Also provide the expected network, genesis bridge
key hash, TSO URL, artifact origin, selected mode/generation/enforcement, and
approved signer image identity. The bundle contains public bridge facts, not
partner secret env files or partner-owned TOML.

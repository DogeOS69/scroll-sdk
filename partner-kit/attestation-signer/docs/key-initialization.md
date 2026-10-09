# Generate a signer identity with Docker

Use this standalone entry point to create a **local attestation key** and a
separate **transport key**, then register their public keys in Governance.
The host needs Docker and Bash (Linux, macOS, or WSL). It does not need
scroll-sdk-cli, Node.js, Python, OpenSSL, a Dogecoin node, or the bridge's
deployment configuration bundle. This tool does not create KMS keys.

Obtain `scripts/init-keys.sh` and `scripts/init-keys.mjs` from a reviewed copy of
this kit and keep them in the same directory. They also work when copied out
of the SDK checkout; no other repository files are needed for key generation.

## Create or display your identity

From the kit directory, run:

```bash
bash scripts/init-keys.sh \
  --name signer-a \
  --network testnet \
  --out "$HOME/dogeos-signer-a/docker-compose"
```

Choose the stable signer name agreed with the bridge operator and the network
`mainnet`, `testnet`, or `regtest`. Prefer an output directory outside Git.
For an operator workspace that is itself a Git checkout, explicitly exclude
the entire private output directory in `.git/info/exclude` before initialization.
The wrapper then requires the host's Git executable to check that the directory
and all generated files are ignored and that no output files are already tracked.
Git is not needed for output outside a checkout. Use the same name and network
when running the command again.

The wrapper runs a pinned, multi-platform Docker Official Node image. All
cryptography runs inside the container using Node's OpenSSL-backed standard
library; there are no npm installs or host crypto tools. Docker downloads the
image on the first run. Key generation itself always runs with
`--network none`, a read-only root filesystem, and the invoking user's UID/GID.
For an offline host, preload this exact image with `docker load`:

```text
node:22-bookworm-slim@sha256:c3de60bf2f9dd0ac6370e6117950ff62d6e339527e7472301c9c78a017978392
```

Files are written directly to your host directory and survive container exit:

| File | Contents | Sharing |
| --- | --- | --- |
| `attestation-signer.env` | Local attestation private key in compressed Dogecoin WIF, network, transport-file reference, pull delivery, and approved beta.6 binary pins | Private; mode `0600` |
| `transport.key` | Independent 32-byte secp256k1 private key as one hex line | Private; mode `0600` |
| `public-identity.json` | Name, network, attestation public key, and transport public key | Public information; saved locally for comparison |

The terminal shows only public information:

```text
name: signer-a
network: testnet
attestationPubkey: <compressed attestation public key>
transportPubkey: <compressed transport public key>
```

Copy the two complete public keys into the corresponding Governance fields
on **the same signer record**. Associate that record with your team. The bridge
operator copies the approved pair into one `attestationSigners` entry in their
spec; `name` is the stable identifier, not the team's display name. There is no
descriptor-file handoff and no automatic Governance API call.

## Existing identities and recovery

Repeating the command validates and displays the existing identity without
rewriting files. It checks the WIF network/checksum, private-key validity,
public-key pairing, name, network, and private file permissions. A missing file,
changed public key, symlink, or incomplete initialization stops the command.
There is no force-overwrite option. Restore the original files from backup;
generating replacements would change the identity registered in Governance.

Initialization uses an exclusive `.key-init.lock` directory. After a process
crash, confirm the initializer is no longer running before removing that empty
lock directory. If files were only partially written, restore a complete backup
or use a new directory for an identity that has never been registered. The tool
does not infer that losing a file authorizes key rotation.

Keep both private files in the operator's backup. Neither belongs in Governance,
a bridge handoff, source control, or a container image. The public identity file
is useful for detecting an accidental mismatch when restoring those backups.

## Starting the signer later

The output files already match the reference Compose service: put
`docker-compose.yml` next to them, and it reads `attestation-signer.env` and mounts
`transport.key` at `/etc/dogeos-partner/transport.key`. Do not rerun the old Phase A
initializer over these files.

Key generation and registration do not start the signer. Before starting it,
the operator must still review their `attestation-signer.toml` trust policy and
install the bridge's verified configuration bundle (`signer-policy.env`,
canonical context, and the selected verifier artifacts). The generated env pins
the approved beta.6 binary; update its release pins together with a reviewed
signer-image change. These runtime inputs and their ownership are described in
the [main runbook](../README.md#ownership-boundary).

The older CLI-based Phase A/B scripts remain a separate deployment workflow;
this Docker-only entry point replaces local **key creation and Governance
registration**, not all of their policy-import or runtime-preflight commands.

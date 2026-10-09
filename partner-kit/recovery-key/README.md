# Offline recovery-key handoff for a testnet rehearsal

Each of the three recovery custodians prepares one independent key and gives the
deployment operator only its public key. No Dogecoin node or blockchain sync is
required. This is separate from running an attestation signer.

Use a trusted Linux/macOS/WSL machine and an installed scroll-sdk-cli build that
includes `scrollsdk helper recovery-key --help`. Installation requires obtaining
the software and dependencies first; key generation and inspection can then run
without a network connection. This helper uses software keys for rehearsal. It
does not integrate a hardware wallet/HSM or implement emergency spending.

## Create your key

Confirm the network with the deployment operator. For this testnet deployment:

```bash
scrollsdk helper recovery-key --network testnet --output "$HOME/.dogeos-recovery-key"
```

Choose a new directory outside version control whose parent already exists. The
command creates a private directory (0700) and two files (0600):

| File | What to do with it |
| --- | --- |
| `recovery-key.private.json` | Keep it private and back it up under your custody. It contains an unencrypted WIF private key. Never send it to the operator or another custodian. |
| `recovery-key.public.json` | Send this file to the deployment operator through your agreed, authenticated handoff channel. It contains only the schema, network and compressed public key. |

The terminal and `--json` output contain only the public key and file locations.
Generating a key sends no transactions. A repeated create refuses an existing
directory instead of replacing your key.

## Verify your saved key or backup

Back up both files privately. Restore them to a private directory and inspect:

```bash
scrollsdk helper recovery-key --action inspect --network testnet --output "$HOME/.dogeos-recovery-key"
```

For a restored copy, point `--output` at that copy. Preserve directory mode 0700
and private-file mode 0600 when restoring. The command checks the
private key, public-key match, declared network and file permissions without
changing the files or printing the private key. Confirm the displayed public
key matches the one you handed over. It does not sign a recovery transaction.

## Operator handoff

Collect one public file from each independent custodian. Confirm all three use
the intended network and contain distinct public keys. Copy their `publicKey`
values into `preparation.bridge.production.recoveryPublicKeys` in the agreed
order, keeping `bridge.thresholds.recovery: 2` for this 2-of-3 policy.

Do not ask one operator to generate all three keys for the custodians. Before
production use, agree on the custody mechanism and validate that it can sign the
actual DogeOS Bridge recovery script. Custodians also need the final public
Bridge configuration (including the full script, ordered keys, threshold and
timelock); a private-key backup alone is not a complete recovery procedure.

Public-key collection, confirmation of the full multisig policy by every signer,
and preservation of that policy follow the separation described in
[BIP 129's multisig setup workflow](https://bips.dev/129/). This helper does not
implement BIP 129 or claim compatibility with Bitcoin hardware-wallet protocols.

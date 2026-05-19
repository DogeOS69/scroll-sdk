# eth-da-submitter

![Version: 0.1.0](https://img.shields.io/badge/Version-0.1.0-informational?style=flat-square) ![Type: application](https://img.shields.io/badge/Type-application-informational?style=flat-square) ![AppVersion: 0.3.0](https://img.shields.io/badge/AppVersion-0.3.0-informational?style=flat-square)

A Helm chart for the DogeOS Ethereum DA submitter.

`eth-da-submitter` is an active worker. It watches DogeOS L2, submits EIP-4844
transactions to Ethereum L1, and exposes only operational HTTP endpoints:
`/health`, `/ready`, `/metrics`, and `/status`.

## Maintainers

| Name | Email | Url |
| ---- | ------ | --- |
| DogeOS69 | <support@dogeos.com> |  |

## Requirements

Kubernetes: `>=1.22.0-0`

| Repository | Name | Version |
|------------|------|---------|
| oci://ghcr.io/dogeos69/scroll-sdk/helm | external-secrets-lib | 0.0.4 |
| oci://ghcr.io/scroll-tech/scroll-sdk/helm | common | 1.5.1 |

## Configuration

Non-secret configuration is rendered into the `eth-da-submitter-env`
ConfigMap. The submitter private key should be supplied through
`eth-da-submitter-secret-env` with key
`DOGEOS_ETH_DA_SUBMITTER_ETHEREUM__SUBMITTER_PRIVATE_KEY`.

Environment variable names mirror the service loader:

```text
DOGEOS_ETH_DA_SUBMITTER_<SECTION>__<KEY>
```

For example,
`DOGEOS_ETH_DA_SUBMITTER_ETHEREUM__RPC_URL` overrides
`[ethereum].rpc_url`.

## Values

See [values.yaml](values.yaml) for the complete default configuration.

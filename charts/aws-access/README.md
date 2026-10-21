# AWS service identities

`scrollsdk setup aws` prepares IAM roles. This chart installs the ServiceAccounts
that External Secrets uses with `SecretStore.spec.provider.aws.auth.jwt.serviceAccountRef`.
Each reader role grants access only to that service's exact Secrets Manager ARNs.
Runtime S3/KMS ServiceAccounts remain owned by the service charts. An optional
`snapshot-writer` identity is installed here for operator-supplied upload Jobs;
those Jobs must select it explicitly.

The External Secrets Operator and its v1 CRDs must already be installed. The CLI
writes `values/aws-access-production.yaml`; `make install-aws-access` installs it.
Service installation targets depend on it when that file exists. Existing
manually managed deployments without the file retain their original behavior.
Reader accounts do not automount Kubernetes API credentials. ESO requests a token
for the selected account; its installation must permit serviceaccounts/token.

The chart contains public IAM annotations only, never cloud credentials or
runtime Secret values. Do not uninstall these accounts while SecretStores use them.

# Supplementary Guide: AWS EKS Deployment for Scroll SDK

This document complements the official [AWS EKS Deployment guide](https://docs.scroll.io/en/sdk/guides/aws-deployment/) by providing additional context and tips for deployment. We recommend using this guide alongside the official documentation for optimal results.

> Please follow the official AWS EKS deployment guide up to the `Setup your local repo` section. The following steps will build upon the initial cluster setup and configuration covered there.

## Setup your local repo

In addition to the three files/folders mentioned in the official guide, copy the following script file to your `aws-scroll-sdk` root directory:


```bash
cp ../scroll-sdk/examples/anvil-fund-accounts.sh .
```

```bash
# anvil-fund-accounts.sh
# Replace the following values in the script according to your config
read_config() {
    yq eval "$1" <your config folder>/config.toml
}

L1_RPC_URL="<l1-devnet RPC URL>"
```

`anvil-fund-accounts.sh` will fund the deployer account in L1.

## Setting Domains

Run `scrollsdk setup domains`, at the last step, answer `yes` to write config to `config.toml` file.

```
...

? Do you want to update the config.toml file with these new configurations? yes
config.toml has been updated with the new domain configurations.
```

## Initializing our Databases and Database Users

At step 3. Run the database initialization:

```bash
scrollsdk setup db-init
```

During the database initialization process, you will be prompted twice for database connection information:

1. First, for the public-facing database connection that external services will use to access the database
2. Second, for the internal database connection used for communication between Kubernetes pods and the database

They can be the same connection.

## Generate Keystore Files

```bash
scrollsdk setup gen-keystore
```
When asking the password for sequencer, please provide non-empty password, otherwise it will cause an error after deployment, however, the cli tool won't check the empty password at this step.

> err: key L2GETH_PASSWORD_0 does not exist in secret scroll/l2-sequencer-secret-env

## Generate Configuration Files

Now, we'll proceed with generating the configuration files for each service based on the values defined in `config.toml`. Please ensure Docker is running in the background before proceeding with this step, as it is a prerequisite for the configuration generation process.

Run `scrollsdk setup configs`.

During the configuration process, you will be prompted to provide values for several parameters. For most options, you can proceed with the default values unless you have specific requirements. You will need to provide:
- The L1_PLONK_VERIFIER_ADDR value, which should be set to `0x0000000000000000000000000000000000000001`

## Prepare Configrations of Charts
```bash
scrollsdk setup prep-charts
```

The cli tool will use the L2 Chain ID instead of L1 Chain ID and write into `l1-devnet-production.yaml` file. Please correct it manually.

```yaml
# l1-devnet-production.yaml
...
configMaps:
  env:
    enabled: true
    data:
      CHAIN_ID: "31337"         <<< L1 Chain ID here
...
```

## Push Secrets
```bash
scrollsdk setup push-secrets
```
When asking secret prefix, please use default value - scroll, the tool won't generate prefix correctly in the yaml file when using custom secret prefix.
> ? Enter secret prefix name: **scroll**

If the custom secret prefix is required, please replace the secret prefix manully in all the `*-production.yaml` files.

```yaml
# example
externalSecrets:
  l2-sequencer-secret-0-env:
    provider: "aws"
    data:
      - remoteRef:
          key: "scroll/l2-sequencer-secret-env"      <<< replace with custom secret prefix
          property: "L2GETH_KEYSTORE_0"
        secretKey: "L2GETH_KEYSTORE"
      - remoteRef:
          key: "scroll/l2-sequencer-secret-env"      <<< replace with custom secret prefix
          property: "L2GETH_PASSWORD_0"
        secretKey: "L2GETH_PASSWORD"
      - remoteRef:
          key: "scroll/l2-sequencer-secret-env"      <<< replace with custom secret prefix
          property: "L2GETH_NODEKEY_0"
        secretKey: "L2GETH_NODEKEY"
    refreshInterval: "2m"
    serviceAccount: "external-secrets"
    secretRegion: "us-east-2"
```

<br/><br/>

> Please refer to the official AWS deployment guide for the remaining configuration steps up to the Deployment section. 

## Deployment

### 1. Deploy `l1-devnet`

```bash
make install-l1-devnet
```

### 2. Fund the Deployer

Alternatively, you can utilize the provided `anvil-fund-accounts.sh` script to fund the deployer account required for contract deployment. Before executing the script, ensure that the `L1_RPC_URL` value in the script matches your configuration settings to avoid any connection issues.

```bash
./anvil-fund-accounts.sh
```

`anvil-fund-accounts.sh` script requires the `yq` library, please use version v4.44.2 or later. A known [issue](https://github.com/mikefarah/yq/issues/2039) exists in version v4.44.1 or earlier, where the value `10_000_000` is incorrectly parsed as a string instead of an integer, which may affect the script's execution.


### 3. Installing the Helm Charts

Review the `Makefile` to identify the required Helm charts for installation. The Makefile includes core Scroll components as well as additional services like Blockscout (stack & explorer) and Blockscout Smart Contract Verifier.

To deploy the charts:

1. Run `make install` to deploy all charts at once
2. Alternatively, deploy charts individually for better control and monitoring during initial setup
3. Monitor deployment status using `kubectl get pods -n <namespace>` or the recommended `k9s` tool

The deployment process will install:
- Core Scroll components (sequencer, bootnode, l2-rpc, coordinator, bridge, etc.)
- Blockscout stack and  explorer
- Smart contract verification service
- Scroll monitoring services

Verify successful deployment by ensuring all pods reach "Running" status without errors.

### 4. Fund L2 accounts

Transfer fund from L1 to L2.

```bash
scrollsdk helper fund-accounts -f 0.2 -l 2
```

Select the "Bridging funds from L1 to L2" menu to transfer fund from L1 to L2 for the deployer account.

> Note: Contract deployment requires sufficient funds in the deployer account. If the account balance was insufficient during initial deployment, you may need to redeploy the contracts after funding the account in step 4.

## Re-Deployment
### Delete all charts and release all resources
```bash
# delete all charts
make delete
# delete l1-devnet
make delete-l1-devnet
# release all persistent volume associated with services
kubectl delete pvc --all
```

### Known Issues When Updating Configuration
When re-running the `scrollsdk setup gen-keystore `command, the CLI tool may not update certain fields in the `l2-sequencer-production-*.yaml` files. In such cases, manual updates to these configuration files are required to ensure proper deployment and operation of the sequencer components.
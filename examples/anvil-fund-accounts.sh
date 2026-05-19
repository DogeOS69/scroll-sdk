#!/bin/bash
# Funds default L1 accounts from the prefunded local L1 devnet account.

set -euo pipefail

read_config() {
    yq eval "$1" charts/scroll-sdk/config.toml
}

L1_RPC_URL=$(read_config '.frontend.EXTERNAL_RPC_URI_L1')
FUNDER_PRIVATE_KEY="${FUNDER_PRIVATE_KEY:-$(read_config '.accounts.DEPLOYER_PRIVATE_KEY')}"
FUNDER_ADDR=$(cast wallet address --private-key "$FUNDER_PRIVATE_KEY")
FUND_AMOUNT="${FUND_AMOUNT:-100ether}"

addresses=(
  "$(read_config '.accounts.L1_COMMIT_SENDER_ADDR')"
  "$(read_config '.accounts.L1_FINALIZE_SENDER_ADDR')"
  "$(read_config '.accounts.L1_GAS_ORACLE_SENDER_ADDR')"
  "$(read_config '.accounts.DEPLOYER_ADDR')"
  "$(read_config '.accounts.OWNER_ADDR')"
)

for address in "${addresses[@]}"
do
  if [ "$(echo "$address" | tr '[:upper:]' '[:lower:]')" = "$(echo "$FUNDER_ADDR" | tr '[:upper:]' '[:lower:]')" ]; then
    echo "Skipping prefunded account $address"
    continue
  fi

  cast send \
    --rpc-url "$L1_RPC_URL" \
    --private-key "$FUNDER_PRIVATE_KEY" \
    "$address" \
    --value "$FUND_AMOUNT"
done

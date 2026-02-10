#!/bin/bash
# inject-bridge-config.sh
# Reads bridge initialization output from scroll-sdk/.data/ and injects
# the addresses/config into values.yaml (l1-interface configMap section).
#
# Dependencies: jq, yq (pip install yq or snap install yq), grep, sed

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
DATA_DIR="${SCRIPT_DIR}/scroll-sdk/.data"
VALUES_FILE="${SCRIPT_DIR}/values.yaml"

# --- Validate required files exist ---
for f in output-test-data.json output-withdrawal-processor.toml doge-config-testnet.toml; do
  if [ ! -f "${DATA_DIR}/${f}" ]; then
    echo "ERROR: ${DATA_DIR}/${f} not found. Run bridge-init first." >&2
    exit 1
  fi
done

echo "=== Reading bridge output files from ${DATA_DIR} ==="

# --- Extract values from output-test-data.json ---
BRIDGE_ADDRESS=$(jq -r '.bridge_address' "${DATA_DIR}/output-test-data.json")
SEQUENCER_ADDRESS=$(jq -r '.sequencer_address' "${DATA_DIR}/output-test-data.json")
FEE_WALLET_ADDRESS=$(jq -r '.fee_wallet_address' "${DATA_DIR}/output-test-data.json")
SEQUENCER_UTXO_TXID=$(jq -r '.sequencer_utxo_txid' "${DATA_DIR}/output-test-data.json")

echo "  bridge_address:       ${BRIDGE_ADDRESS}"
echo "  sequencer_address:    ${SEQUENCER_ADDRESS}"
echo "  fee_wallet_address:   ${FEE_WALLET_ADDRESS}"
echo "  sequencer_utxo_txid:  ${SEQUENCER_UTXO_TXID}"

# --- Extract values from output-withdrawal-processor.toml ---
BRIDGE_SCRIPT_HEX=$(grep '^bridge_script_hex' "${DATA_DIR}/output-withdrawal-processor.toml" | sed 's/bridge_script_hex = "\(.*\)"/\1/')
NETWORK_STR=$(grep '^network_str' "${DATA_DIR}/output-withdrawal-processor.toml" | sed 's/network_str = "\(.*\)"/\1/')
FEE_SIGNER_KEY=$(grep '^fee_signer_key' "${DATA_DIR}/output-withdrawal-processor.toml" | sed 's/fee_signer_key = "\(.*\)"/\1/')
SEQUENCER_SIGNER_KEY=$(grep '^sequencer_signer_key' "${DATA_DIR}/output-withdrawal-processor.toml" | sed 's/sequencer_signer_key = "\(.*\)"/\1/')
GENESIS_SEQ_TXID=$(grep '^genesis_sequencer_txid' "${DATA_DIR}/output-withdrawal-processor.toml" | sed 's/genesis_sequencer_txid = "\(.*\)"/\1/')
GENESIS_SEQ_VOUT=$(grep '^genesis_sequencer_vout' "${DATA_DIR}/output-withdrawal-processor.toml" | sed 's/genesis_sequencer_vout = //')

echo "  bridge_script_hex:    ${BRIDGE_SCRIPT_HEX:0:40}..."
echo "  network_str:          ${NETWORK_STR}"
echo "  fee_signer_key:       ${FEE_SIGNER_KEY}"
echo "  sequencer_signer_key: ${SEQUENCER_SIGNER_KEY}"
echo "  genesis_seq_txid:     ${GENESIS_SEQ_TXID}"
echo "  genesis_seq_vout:     ${GENESIS_SEQ_VOUT}"

# --- Extract values from doge-config-testnet.toml ---
DA_NAMESPACE=$(grep '^daNamespace' "${DATA_DIR}/doge-config-testnet.toml" | sed 's/daNamespace = "\(.*\)"/\1/')
INDEXER_START_HEIGHT=$(grep '^dogecoinIndexerStartHeight' "${DATA_DIR}/doge-config-testnet.toml" | sed 's/dogecoinIndexerStartHeight = "\(.*\)"/\1/')

echo "  da_namespace:         ${DA_NAMESPACE}"
echo "  indexer_start_height: ${INDEXER_START_HEIGHT}"

echo ""
echo "=== Injecting values into ${VALUES_FILE} ==="

# --- Use sed to replace values in values.yaml ---
# Pattern: replace the value within quotes for each DOGEOS_L1_INTERFACE_* key

# Bridge address
sed -i "s|\(DOGEOS_L1_INTERFACE_DOGECOIN_INDEXER__BRIDGE_ADDRESS:\s*\)\"[^\"]*\"|\1\"${BRIDGE_ADDRESS}\"|" "${VALUES_FILE}"

# Network string
sed -i "s|\(DOGEOS_L1_INTERFACE_NETWORK_STR:\s*\)\"[^\"]*\"|\1\"${NETWORK_STR}\"|" "${VALUES_FILE}"

# Indexer start height (L1_GENESIS_BLOCK and INDEXER__START_HEIGHT)
sed -i "s|\(DOGEOS_L1_INTERFACE_L1_GENESIS_BLOCK:\s*\)\"[^\"]*\"|\1\"${INDEXER_START_HEIGHT}\"|" "${VALUES_FILE}"
sed -i "s|\(DOGEOS_L1_INTERFACE_DOGECOIN_INDEXER__START_HEIGHT:\s*\)\"[^\"]*\"|\1\"${INDEXER_START_HEIGHT}\"|" "${VALUES_FILE}"

# DA namespace
sed -i "s|\(DOGEOS_L1_INTERFACE_CELESTIA_INDEXER__NAMESPACE_ID:\s*\)\"[^\"]*\"|\1\"${DA_NAMESPACE}\"|" "${VALUES_FILE}"

# Also update da-publisher namespace to match
sed -i "s|\(DOGEOS_DA_PUBLISHER_CELESTIA_NAMESPACE:\s*\)\"[^\"]*\"|\1\"${DA_NAMESPACE}\"|" "${VALUES_FILE}"

echo "  [OK] Updated DOGECOIN_INDEXER__BRIDGE_ADDRESS = ${BRIDGE_ADDRESS}"
echo "  [OK] Updated NETWORK_STR = ${NETWORK_STR}"
echo "  [OK] Updated L1_GENESIS_BLOCK = ${INDEXER_START_HEIGHT}"
echo "  [OK] Updated DOGECOIN_INDEXER__START_HEIGHT = ${INDEXER_START_HEIGHT}"
echo "  [OK] Updated CELESTIA_INDEXER__NAMESPACE_ID = ${DA_NAMESPACE}"
echo "  [OK] Updated DA_PUBLISHER_CELESTIA_NAMESPACE = ${DA_NAMESPACE}"

echo ""
echo "=== Bridge config injection complete ==="
echo ""
echo "NOTE: The following values were extracted but NOT auto-injected (may need manual placement):"
echo "  sequencer_address:    ${SEQUENCER_ADDRESS}"
echo "  fee_wallet_address:   ${FEE_WALLET_ADDRESS}"
echo "  bridge_script_hex:    ${BRIDGE_SCRIPT_HEX:0:40}..."
echo "  fee_signer_key:       ${FEE_SIGNER_KEY}"
echo "  sequencer_signer_key: ${SEQUENCER_SIGNER_KEY}"
echo "  genesis_seq_txid:     ${GENESIS_SEQ_TXID}"
echo "  genesis_seq_vout:     ${GENESIS_SEQ_VOUT}"

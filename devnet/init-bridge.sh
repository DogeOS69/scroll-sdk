#!/bin/bash
cd scroll-sdk
export DOGECOIN_RPC_URL="http://172.18.0.1:44555"
export DOGECOIN_RPC_USER="shadowfork"
export DOGECOIN_RPC_PASS="shadowfork_testnet_password"
mkdir -p .data/

echo "Fetching UTXOs for nbVx7cF7xvfS9BQZ2fALtgiPP4gSEKCdEZ..."
UTXOS=$(curl -s https://doge-electrs-testnet-demo.qed.me/address/nbVx7cF7xvfS9BQZ2fALtgiPP4gSEKCdEZ/utxo)

# Find a UTXO with value > 7,000,000,000
SELECTED_UTXO=$(echo "$UTXOS" | jq -c '.[] | select(.value > 7000000000)' | head -n 1)

if [ -z "$SELECTED_UTXO" ]; then
    echo "Error: No suitable UTXO found (> 7,000,000,000 sats)"
    exit 1
fi

# Generate a random seed string (16 chars)
export SEED_STRING=$(head /dev/urandom | tr -dc A-Za-z0-9 | head -c 16)
echo "Generated random seed: $SEED_STRING"

# 1. First run to get the Distribution Helper Address
# We provide dummy values just to get the logs
export BRIDGE_TXID="dummy"
export BRIDGE_VOUT=0
export BRIDGE_VALUE=0

mkdir -p .data/
envsubst < ../setup_defaults.toml > .data/setup_defaults.toml

echo "Probing bridge-init to get Distribution Helper Address..."
# Run and capture logs, avoiding null byte issues from docker/ansi
PROBE_LOGS=$(dogesdk doge bridge-init --non-interactive --seed "$SEED_STRING" 2>&1 | tr -d '\000')

HELPER_ADDRESS=$(echo "$PROBE_LOGS" | grep -oP 'Distribution Helper Address \(derived from seed\): \K\S+')

if [ -z "$HELPER_ADDRESS" ]; then
    echo "Error: Could not extract Distribution Helper Address from logs"
    echo "Logs summary: $(echo "$PROBE_LOGS" | tail -n 5)"
    exit 1
fi

echo "Extracted Address: $HELPER_ADDRESS"
echo "send 70 doge to ${HELPER_ADDRESS}"
dogesdk test dogeos 9 --to ${HELPER_ADDRESS} --amount 70
echo "Fetching UTXOs for $HELPER_ADDRESS..."

echo "Waiting for UTXO to appear on ${HELPER_ADDRESS}..."
for i in {1..30}; do
    UTXOS=$(curl -s "https://doge-electrs-testnet-demo.qed.me/address/${HELPER_ADDRESS}/utxo")
    SELECTED_UTXO=$(echo "$UTXOS" | jq -c '.[] | select(.value >= 7000000000)' | head -n 1)
    if [ -n "$SELECTED_UTXO" ]; then
        echo "Found UTXO!"
        break
    fi
    echo "Waiting for transaction confirmation... (attempt $i/30)"
    sleep 20
done

if [ -z "$SELECTED_UTXO" ]; then
    echo "Error: No suitable UTXO found for $HELPER_ADDRESS (> 7,000,000,000 sats)"
    exit 1
fi

export BRIDGE_TXID=$(echo "$SELECTED_UTXO" | jq -r '.txid')
export BRIDGE_VOUT=$(echo "$SELECTED_UTXO" | jq -r '.vout')
export BRIDGE_VALUE=$(echo "$SELECTED_UTXO" | jq -r '.value')

echo "Selected UTXO: $BRIDGE_TXID:$BRIDGE_VOUT with amount $BRIDGE_VALUE"

# 3. Final configuration generation and bridge-init
envsubst < ../setup_defaults.toml > .data/setup_defaults.toml

echo "Starting final bridge-init..."
dogesdk doge bridge-init --non-interactive --seed "$SEED_STRING"

# --- Variables ---

# Colors for output
BLUE         := \033[34m
GREEN        := \033[32m
RED          := \033[31m
YELLOW       := \033[33m
RESET        := \033[0m

# System architecture detections
UNAME_M      := $(shell uname -m)
IS_ARM       := $(filter arm64 aarch64,$(UNAME_M))

# Architecture-specific settings
ARCH_SUFFIX  := $(if $(IS_ARM),-arm64,)
ARCH_PREFIX  := $(if $(IS_ARM),,scroll-)
SC_VERIFIER_TAG := $(if $(IS_ARM),v1.7.0-arm,v1.7.0)

L2_IMAGE_TAG := $(ARCH_PREFIX)v5.8.36$(ARCH_SUFFIX)
SCROLL_CONTRACTS_TAG_SUFFIX := eb2fd988a5cf90ac39d4c02f67e2b80ca99c7f3f
L1_RPC_HOST  := l1-devnet.scrollsdk

NAMESPACE    ?= default
RELEASE_NAME ?= scroll-sdk-devnet

# Helm values files
HELM_VALUES  := --values scroll-sdk/genesis.yaml \
                --values scroll-sdk/scroll-common-config.yaml \
                --values scroll-sdk/scroll-common-config-contracts.yaml \
                --values values.yaml \
                --values scroll-sdk/rollup-relayer-config.yaml

# --- Targets ---
.PHONY: all help bootstrap bootstrap-local config install reload-env-files delete upgrade verify check-deps

all: check-deps install ## Default target: check dependencies and install

help: ## Show this help message
	@echo "$(BLUE)Available targets:$(RESET)"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort | awk 'BEGIN {FS = ":.*?## "}; {printf "  $(GREEN)%-20s$(RESET) %s\n", $$1, $$2}'

check-deps: ## Check if required tools are installed
	@echo "$(BLUE)Checking dependencies...$(RESET)"
	@for tool in helm docker kubectl jq envsubst dogesdk; do \
		if ! command -v $$tool >/dev/null 2>&1; then \
			echo "$(RED)Error: $$tool is not installed.$(RESET)"; \
			exit 1; \
		fi; \
	done
	@echo "$(GREEN)All dependencies met.$(RESET)"

bootstrap: ## Pull and extract the helm chart
	@echo "$(BLUE)Pulling helm chart...$(RESET)"
	helm pull oci://ghcr.io/dogeos69/scroll-sdk/helm/scroll-sdk --version 0.1.16-dogeos
	@echo "$(BLUE)Extracting helm chart...$(RESET)"
	tar -xvf *.tgz
	$(MAKE) config

bootstrap-local: ## Copy local helm charts from sibling directory
	@echo "$(BLUE)Copying local helm charts from ../charts...$(RESET)"
	rm -rf scroll-sdk celestia-devnet celestia-node l1-interface
	cp -R ../charts/scroll-sdk .
	cp -R ../charts/celestia-devnet .
	cp -R ../charts/celestia-node .
	cp -R ../charts/l1-interface .
	@echo "$(BLUE)Updating dependencies...$(RESET)"
	helm dependency update scroll-sdk
	$(MAKE) config

config: ## Initialize bridge and generate configuration files
	@echo "$(BLUE)Initializing bridge...$(RESET)"
	./init-bridge.sh
	./inject-bridge-config.sh

	@echo "$(BLUE)Creating configuration files via Docker...$(RESET)"
	cd scroll-sdk && time docker run --rm -v .:/contracts/volume \
		dogeos69/scroll-stack-contracts:gen-configs-$(SCROLL_CONTRACTS_TAG_SUFFIX)
	@echo "$(BLUE)Generating environment and scroll-sdk config files...$(RESET)"
	./create-env-files.sh scroll-sdk
	./prepare-config-files.sh

install: check-deps ## Install/Upgrade the Scroll SDK via Helm
	@echo "$(BLUE)Installing/Upgrading $(RELEASE_NAME) in namespace: $(NAMESPACE)...$(RESET)"
	helm upgrade -i $(RELEASE_NAME) scroll-sdk -n $(NAMESPACE) $(HELM_VALUES)

reload-env-files: ## Regenerate environment files
	@echo "$(BLUE)Reloading environment files...$(RESET)"
	./create-env-files.sh scroll-sdk

delete: ## Uninstall the release and clean up PVCs
	@echo "$(YELLOW)Uninstalling $(RELEASE_NAME)...$(RESET)"
	-helm uninstall $(RELEASE_NAME) -n $(NAMESPACE)
	@echo "$(YELLOW)Cleaning up persistent volumes (PVCs)...$(RESET)"
	-kubectl delete pvc data-l2-rpc-0 data-scroll-sdk-devnet-bridge-0 \
		data-scroll-sdk-devnet-validator-0 scroll-sdk-devnet-celestia-node-private-pvc \
		-n $(NAMESPACE) --ignore-not-found

upgrade: install ## Alias for install

verify: ## Verify deployed contracts
	@echo "$(BLUE)Verifying contracts...$(RESET)"
	cd scroll-sdk && time docker run --rm --network="host" -v .:/contracts/volume \
		dogeos69/scroll-stack-contracts:verify-$(SCROLL_CONTRACTS_TAG_SUFFIX)

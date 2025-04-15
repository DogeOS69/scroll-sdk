# Define variables for architecture-specific settings
ARCH_ARM64 := $(shell if [ "$$(uname -m)" = "arm64" ] || [ "$$(uname -m)" = "aarch64" ]; then echo "-arm64"; else echo ""; fi)
ARCH_OTHER := $(shell if [ "$$(uname -m)" != "arm64" ] && [ "$$(uname -m)" != "aarch64" ]; then echo "scroll-"; else echo ""; fi)
NAMESPACE ?= default
L2_IMAGE_TAG := $(ARCH_OTHER)v5.8.36$(ARCH_ARM64)
L1_RPC_HOST := l1-devnet.scrollsdk
SCROLL_CONTRACTS_TAG_SUFFIX := 38c822d4dd33165b4def23c2f99e94220ecd4ba5
SC_VERIFIER_TAG := $(if $(ARCH_ARM64),v1.7.0-arm,v1.7.0)

bootstrap:
		echo "Pulling helm chart..."
		helm pull oci://ghcr.io/DogeOS69/scroll-sdk/helm/scroll-sdk --version 0.1.5-dogeos
		echo "Extracting helm chart..."
		tar -xvf *.tgz
		$(MAKE) config

config:
		echo "Creating configuration files..."
		cd scroll-sdk && time docker run --rm -it -v .:/contracts/volume dogeos69/scroll-stack-contracts:gen-configs-$(SCROLL_CONTRACTS_TAG_SUFFIX)
		echo "Creating env files..."
		./create-env-files.sh scroll-sdk
		./prepare-config-files.sh

install:
		helm upgrade -i scroll-sdk scroll-sdk -n $(NAMESPACE) \
			--set l2-rpc.image.tag=$(L2_IMAGE_TAG) \
			--set l2-sequencer.image.tag=$(L2_IMAGE_TAG) \
			--set l2-bootnode.image.tag=$(L2_IMAGE_TAG) \
			--set contracts.image.tag=deploy-$(SCROLL_CONTRACTS_TAG_SUFFIX) \
			--set l1-devnet.ingress.main.hosts[0].host=$(L1_RPC_HOST) \
			--set l1-devnet.ingress.main.hosts[0].paths[0].path=/ \
			--set l1-devnet.ingress.main.hosts[0].paths[0].pathType=Prefix \
			--values scroll-sdk/genesis.yaml \
			--values scroll-sdk/scroll-common-config.yaml \
			--values scroll-sdk/scroll-common-config-contracts.yaml

reload-env-files:
		./create-env-files.sh scroll-sdk

delete:
		helm uninstall scroll-sdk -n $(NAMESPACE)

upgrade:
		$(MAKE) install

verify:
		echo "Verifing contracts..."
		cd scroll-sdk && time docker run --rm -it --network="host" -v .:/contracts/volume dogeos69/scroll-stack-contracts:verify-38c822d4dd33165b4def23c2f99e94220ecd4ba5
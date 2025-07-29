VERSION ?= 0.1.0
REGISTRY ?= quay.io/ecosystem-appeng

build_ui:
	podman build --platform linux/amd64 -t vllm-alert-receiver:$(VERSION) .

build_and_push_ui: build_ui
	podman tag vllm-alert-receiver:$(VERSION) $(REGISTRY)/vllm-alert-receiver:$(VERSION)
	podman push $(REGISTRY)/vllm-alert-receiver:$(VERSION)
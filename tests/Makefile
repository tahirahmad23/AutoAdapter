# AutoAdapter — cocotb Verification Makefile
# Usage:
#   make test        # Run default test
#   make test-all    # Run all tests across all shells x accelerators
#   make clean       # Clean build artifacts

COCOTB_MAKEFILES := $(shell $(realpath $(dir $(lastword $(MAKEFILE_LIST)))/../.venv/bin/cocotb-config) --makefiles 2>/dev/null || echo "cocotb-config not found")
SIM ?= verilator
TOPLEVEL_LANG ?= verilog

# Default test parameters
ADAPTER_RTL    ?= hdl/auto_adapter_top.sv
DATA_WIDTH     ?= 512
TUSER_WIDTH    ?= 64
HLS_LATENCY    ?= 5
HLS_MODULE     ?= flow_hash
HLS_SOURCE     ?= flow_hash_model.sv

# AutoAdapter repo root
REPO_ROOT := $(realpath $(dir $(lastword $(MAKEFILE_LIST)))..)

# ---- Targets ----

.PHONY: all clean test test-all run-single

all: test

# Run a single cocotb test
run-single: $(ADAPTER_RTL)
	@echo "Running $(TEST_MODULE) with $(HLS_MODULE) on $(ADAPTER_RTL)"
	mkdir -p $(REPO_ROOT)/tests/sim_build
	cd $(REPO_ROOT)/tests && \
	VERILATOR_VERSION=5.049 \
	TOPLEVEL=testbench_top \
	MODULE=$(TEST_MODULE) \
	TOPLEVEL_LANG=verilog \
	SIM=verilator \
	COCOTB_MAKEFILES=$(COCOTB_MAKEFILES) \
	COCOTB_REDUCED_LOG_FMT=1 \
	VERILOG_SOURCES="$(REPO_ROOT)/tests/$(HLS_SOURCE) $(REPO_ROOT)/tests/testbench_top.sv $(ADAPTER_RTL)" \
	SIM_BUILD=sim_build \
	EXTRA_ARGS="--trace --trace-structs -Wno-fatal -Wno-lint -Wno-STMTDLY --Mdir sim_build" \
	PLUSARGS="+verilator+rand+reset+2" \
	$(MAKE) -f $(COCOTB_MAKEFILES)/Makefile.sim 2>&1 | tail -20

# Run the full verification suite for all shells x accelerators
test-all:
	@cd $(REPO_ROOT) && \
	for shell in opennic_250mhz opennic_322mhz corundum_mqnic coyote_v2; do \
		shell_name="$${shell%%_*}"; \
		case "$$shell" in opennic_250mhz|opennic_322mhz) shell_name="opennic";; corundum_mqnic) shell_name="corundum";; coyote_v2) shell_name="coyote";; esac; \
		for accel in flow_hash packet_monitor; do \
			config=$${shell}-$${accel}; \
			output_dir=$(REPO_ROOT)/output/$$config; \
			hdl_dir=$$output_dir/hdl; \
			for test_mod in test_tuser_integrity test_backpressure test_corner_cases test_ablation; do \
				echo "=== $$config / $$test_mod ==="; \
				$(REPO_ROOT)/.venv/bin/python3 $(REPO_ROOT)/tests/run_verification.py \
					--shell $$shell_name \
					--hls-module $$accel \
					--test $$test_mod \
					--output-dir $$output_dir \
					--hdl-dir $$hdl_dir 2>&1 | grep -E "PASS|FAIL|ERROR|Test Results" || echo "FAIL: $$config/$$test_mod"; \
			done; \
		done; \
	done

# Quick smoke test
test:
	cd $(REPO_ROOT) && \
	$(REPO_ROOT)/.venv/bin/python3 $(REPO_ROOT)/tests/run_verification.py \
		--shell opennic --hls-module flow_hash --test test_tuser_integrity

# Clean
clean:
	rm -rf $(REPO_ROOT)/tests/sim_build $(REPO_ROOT)/tests/output
	rm -rf $(REPO_ROOT)/tests/*.vcd $(REPO_ROOT)/tests/*.fst
	rm -rf $(REPO_ROOT)/tests/results.xml
	find $(REPO_ROOT)/tests -name __pycache__ -type d -exec rm -rf {} + 2>/dev/null || true

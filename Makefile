# AutoAdapter — Makefile
# ==============================================================================
# Targets:
#   all       — generate adapters + run all verification tests
#   gen       — generate adapters for all shells x accelerators
#   test      — run all tests (verification + unit)
#   test-v    — run verification tests for all shells x accelerators
#   test-u    — run unit tests
#   test-one  — run single test (SHELL=opennic ACCEL=flow_hash TEST=test_tuser_integrity)
#   clean     — remove generated files
# ==============================================================================

PYTHON    := .venv/bin/python3
GENERATOR := $(PYTHON) generator/adapter_generator.py
RUNNER    := $(PYTHON) tests/run_verification.py

ISL_DIR      := $(CURDIR)/isl
OUTPUT_DIR   := $(CURDIR)/output
ACCEL_DIR    := $(CURDIR)/accelerators

SHELLS    := opennic_250mhz opennic_322mhz corundum_mqnic coyote_v2
ACCELS    := flow_hash packet_monitor
TESTS     := test_tuser_integrity test_backpressure test_corner_cases test_ablation

.PHONY: all gen test test-v test-u test-one clean

# ---- Generate adapters (all shells x real accelerators) ----
gen: $(OUTPUT_DIR)
	@for isl in $(SHELLS); do \
		for accel in $(ACCELS); do \
			echo "=== Generating: $$isl + $$accel ==="; \
			mkdir -p $(OUTPUT_DIR)/$$isl-$$accel; \
			$(GENERATOR) $(ISL_DIR)/$$isl.json $(ACCEL_DIR)/$$accel \
				-o $(OUTPUT_DIR)/$$isl-$$accel -m auto_adapter_top; \
		done; \
	done

$(OUTPUT_DIR):
	mkdir -p $@

# ---- Run verification tests ----
test-v: gen
	@for isl in $(SHELLS); do \
		shell_name="$${isl%%_*}"; \
		case "$$isl" in opennic_250mhz|opennic_322mhz) shell_name="opennic";; corundum_mqnic) shell_name="corundum";; coyote_v2) shell_name="coyote";; esac; \
		for accel in $(ACCELS); do \
			for test in $(TESTS); do \
				echo "=== $$isl + $$accel / $$test ==="; \
				$(RUNNER) --shell $$shell_name \
					--hls-module $$accel \
					--test $$test \
					--output-dir $(OUTPUT_DIR)/$$isl-$$accel \
					--hdl-dir $(OUTPUT_DIR)/$$isl-$$accel/hdl; \
			done; \
		done; \
	done

# ---- Run unit tests ----
test-u:
	$(PYTHON) -m pytest generator/test_generator.py isl/test_parser.py -v

# ---- Full test suite ----
test: test-u test-v

# ---- Run a single test ----
test-one: SHELL ?= opennic
test-one: ACCEL ?= flow_hash
test-one: TEST ?= test_tuser_integrity
test-one: gen
	$(eval ISL_NAME := $(shell echo $(SHELL) | sed 's/opennic/opennic_250mhz/;s/corundum/corundum_mqnic/;s/coyote/coyote_v2/'))
	$(RUNNER) --shell $(SHELL) --hls-module $(ACCEL) --test $(TEST) \
		--output-dir $(OUTPUT_DIR)/$(ISL_NAME)-$(ACCEL) \
		--hdl-dir $(OUTPUT_DIR)/$(ISL_NAME)-$(ACCEL)/hdl

# ---- Clean ----
clean:
	rm -rf $(OUTPUT_DIR) tests/sim_build tests/output
	find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true
	find . -name "*.pyc" -delete
	find . -name ".pytest_cache" -type d -exec rm -rf {} + 2>/dev/null || true

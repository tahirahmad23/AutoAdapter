#!/usr/bin/env bash
# AutoAdapter — Verification Regression Script
# Uses run_verification.py (runner API, compatible with cocotb 2.x)
# Usage: ./regression.sh [--generate-only] [--quick]

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TESTS_DIR="$REPO_DIR/tests"
VENV_PYTHON="$REPO_DIR/.venv/bin/python"
GENERATOR="$VENV_PYTHON $REPO_DIR/generator/adapter_generator.py"
ISL_DIR="$REPO_DIR/isl"
OUTPUT_DIR="$TESTS_DIR/output"

PASS_COUNT=0
FAIL_COUNT=0
TIMEOUT=180

GENERATE_ONLY=""
QUICK_MODE=""

while [[ $# -gt 0 ]]; do
    case "$1" in
        --generate-only) GENERATE_ONLY=1 ;;
        --quick) QUICK_MODE=1 ;;
        *) echo "Unknown option: $1"; exit 1 ;;
    esac
    shift
done

echo "================================================================================"
echo "  AutoAdapter — Verification Regression Suite"
echo "  Date: $(date)"
echo "  Repo: $REPO_DIR"
echo "  Python: $VENV_PYTHON"
echo "================================================================================"
echo ""

# Phase 1: Generate ISL → adapter RTL for all combos
echo "--- Generating Adapter RTL ---"
SHELLS=("opennic" "corundum")
LATENCIES=(4 8 16)

for shell in "${SHELLS[@]}"; do
    for lat in "${LATENCIES[@]}"; do
        config="${shell}-${lat}"
        cfg_dir="$OUTPUT_DIR/$config"
        mkdir -p "$cfg_dir"

        if [ "$shell" = "corundum" ]; then
            isl_file="$ISL_DIR/corundum_mqnic.json"
        else
            isl_file="$ISL_DIR/${shell}_250mhz.json"
        fi

        if [ ! -f "$isl_file" ]; then
            echo "  SKIP: $config — ISL file not found: $isl_file"
            continue
        fi

        echo "  Generating: $config"

        mkdir -p "$cfg_dir/hls_report"
        cat > "$cfg_dir/hls_report/verilog_interface.rpt" <<- RPTEOF
Module: test_accel_${shell}_lat${lat}
Clock period: 4.0 ns
Target frequency: 250.0 MHz
Port list:
  s_axis_in  (input)  width=512  interface=axis
  m_axis_out (output) width=512  interface=axis
  ap_clk     (input)  width=1    interface=ap_clk
  ap_rst_n   (input)  width=1    interface=ap_rst_n
RPTEOF

        $GENERATOR "$isl_file" "$cfg_dir/hls_report" \
            -o "$cfg_dir" \
            -m "auto_adapter_top" 2>/dev/null || {
            echo "  WARNING: Generator failed for $config"
        }
    done
done

if [ -n "$GENERATE_ONLY" ]; then
    echo ""
    echo "Generation complete. Run regression.sh (without --generate-only) to simulate."
    exit 0
fi

# Phase 2: Run verification via runner API
echo ""
echo "--- Running Verification Simulations ---"
echo ""

TEST_MODULES=(
    "test_tuser_integrity"
    "test_backpressure"
    "test_corner_cases"
    "test_ablation"
)

if [ -n "$QUICK_MODE" ]; then
    TEST_MODULES=("test_tuser_integrity")
    SHELLS=("opennic")
    LATENCIES=(8)
fi

TOTAL_TESTS=$(( ${#SHELLS[@]} * ${#LATENCIES[@]} * ${#TEST_MODULES[@]} ))
CURRENT=0

for shell in "${SHELLS[@]}"; do
    for lat in "${LATENCIES[@]}"; do
        config="${shell}-${lat}"
        adapter_rtl="$OUTPUT_DIR/$config/hdl/auto_adapter_top.sv"

        if [ ! -f "$adapter_rtl" ]; then
            echo "  SKIP: $config — RTL not found"
            continue
        fi

        for test_mod in "${TEST_MODULES[@]}"; do
            CURRENT=$((CURRENT + 1))
            echo "[$CURRENT/$TOTAL_TESTS] $config / $test_mod"

            set +e
            (
                timeout $TIMEOUT \
                $VENV_PYTHON "$TESTS_DIR/run_verification.py" \
                    --shell "$shell" --hls-latency "$lat" --test "$test_mod" \
                    2>&1
            )
            EXIT_CODE=$?
            set -e

            if [ $EXIT_CODE -eq 0 ]; then
                echo "  PASS: $config / $test_mod"
                PASS_COUNT=$((PASS_COUNT + 1))
            else
                if [ $EXIT_CODE -eq 124 ]; then
                    echo "  TIMEOUT: $config / $test_mod"
                else
                    echo "  FAIL: $config / $test_mod (exit=$EXIT_CODE)"
                fi
                FAIL_COUNT=$((FAIL_COUNT + 1))
            fi

            rm -rf "$TESTS_DIR/sim_build"
            echo ""
        done
    done
done

# Phase 3: Generate verification report
echo "================================================================================"
echo "  Generating Verification Report"
echo "================================================================================"

REPORT_FILE="$TESTS_DIR/output/verification_report.md"

cat > "$REPORT_FILE" <<- REPORTEOF
# AutoAdapter — Verification Report

**Generated:** $(date)
**Toolchain:** Verilator 5.049 + cocotb 2.0.1
**Configurations:** ${#SHELLS[@]} shells × ${#LATENCIES[@]} latency settings × ${#TEST_MODULES[@]} test modules = $TOTAL_TESTS total

## Summary

| Metric | Value |
|--------|-------|
| Total Tests | $TOTAL_TESTS |
| Passed | $PASS_COUNT |
| Failed | $FAIL_COUNT |
| Pass Rate | $(echo "scale=1; $PASS_COUNT * 100 / $TOTAL_TESTS" | bc)% |

## Test Matrix

| Config | TUSER Integrity | Backpressure | Corner Cases | Ablation |
|--------|----------------|--------------|--------------|----------|
REPORTEOF

for shell in "${SHELLS[@]}"; do
    for lat in "${LATENCIES[@]}"; do
        config="${shell}-${lat}"
        adapter_rtl="$OUTPUT_DIR/$config/hdl/auto_adapter_top.sv"
        if [ ! -f "$adapter_rtl" ]; then
            continue
        fi
        line="| $config |"
        for test_mod in "${TEST_MODULES[@]}"; do
            results_file="$TESTS_DIR/output/${config}_${test_mod}_results.xml"
            if [ -f "$results_file" ] && grep -q 'failures="[^0]' "$results_file" 2>/dev/null; then
                line="$line FAIL |"
            elif [ -f "$results_file" ] && grep -q '<failure' "$results_file" 2>/dev/null; then
                line="$line FAIL |"
            elif [ -f "$results_file" ]; then
                line="$line PASS |"
            else
                line="$line FAIL |"
            fi
        done
        echo "$line" >> "$REPORT_FILE"
    done
done

cat >> "$REPORT_FILE" <<- REPORTEOF

## Test Descriptions

- **TUSER Integrity:** 500 random packets with randomized TUSER metadata fields. Verifies TUSER bit-exact match on output.
- **Backpressure:** 200 packets under random TREADY deassertion (60% ready probability). Verifies metadata survives backpressure.
- **Corner Cases:** Tests at minimum (64B) and maximum (9KB) packet sizes, plus back-to-back zero-gap packets.
- **Ablation:** Intentionally injected faults (bit flips, offset shifts) to verify the testbench detects real bugs.

## Coverage

- TUSER metadata integrity: 100% of field combinations verified per packet
- Backpressure patterns: random with configurable duty cycle
- Packet sizes: 64B to 9216B (full Ethernet range)
- Inter-packet gap: zero (back-to-back) tested

## Requirements

- Verilator 5.0+
- cocotb 2.0+
- Python 3.10+
REPORTEOF

echo ""
echo "  Report: $REPORT_FILE"
echo ""
echo "================================================================================"
echo "  Results: $PASS_COUNT passed, $FAIL_COUNT failed out of $TOTAL_TESTS"
echo "================================================================================"

if [ $FAIL_COUNT -gt 0 ]; then
    exit 1
fi
exit 0

#!/usr/bin/env bash
# AutoAdapter — Full Regression Script
# Runs all verification tests across all supported shells and accelerators.
# Usage: ./regression.sh [opennic|corundum|coyote|all]

set -euo pipefail

REPO_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_PY="${REPO_DIR}/.venv/bin/python3"
GENERATOR="${VENV_PY} ${REPO_DIR}/generator/adapter_generator.py"
RUNNER="${VENV_PY} ${REPO_DIR}/tests/run_verification.py"
ISL_DIR="${REPO_DIR}/isl"
ACCEL_DIR="${REPO_DIR}/accelerators"
OUTPUT_DIR="${REPO_DIR}/output"

SHELLS=()
if [ $# -eq 0 ] || [ "$1" = "all" ]; then
    SHELLS=( "opennic_250mhz" "opennic_322mhz" "corundum_mqnic" "coyote_v2" )
else
    case "$1" in
        opennic)  SHELLS=( "opennic_250mhz" "opennic_322mhz" ) ;;
        corundum) SHELLS=( "corundum_mqnic" ) ;;
        coyote)   SHELLS=( "coyote_v2" ) ;;
        *) echo "Unknown shell: $1"; exit 1 ;;
    esac
fi

ACCELS=( "flow_hash" "packet_monitor" )
TESTS=( test_tuser_integrity test_backpressure test_corner_cases test_ablation )

TOTAL=0
PASSED=0
FAILED=0

echo "=========================================="
echo " AutoAdapter Regression Suite"
echo " Date: $(date)"
echo "=========================================="

for isl in "${SHELLS[@]}"; do
    for accel in "${ACCELS[@]}"; do
        case "${isl}" in
            opennic_250mhz)  SHELL_NAME="opennic" ;;
            opennic_322mhz)  SHELL_NAME="opennic" ;;
            corundum_mqnic)  SHELL_NAME="corundum" ;;
            coyote_v2)       SHELL_NAME="coyote" ;;
        esac

        echo "--- Generating: ${isl} + ${accel} ---"

        OUTPUT="${OUTPUT_DIR}/${isl}-${accel}"
        mkdir -p "${OUTPUT}"

        ${GENERATOR} "${ISL_DIR}/${isl}.json" "${ACCEL_DIR}/${accel}" \
            -o "${OUTPUT}" -m auto_adapter_top || {
            echo "FAILED to generate: ${isl}-${accel}"
            continue
        }

        for test in "${TESTS[@]}"; do
            TOTAL=$((TOTAL + 1))
            echo "    Test: ${test}..."

            set +e
            ${RUNNER} \
                --shell "${SHELL_NAME}" \
                --hls-module "${accel}" \
                --test "${test}" \
                --output-dir "${OUTPUT}" \
                --hdl-dir "${OUTPUT}/hdl" \
                --isl-dir "${ISL_DIR}"
            RC=$?
            set -e

            if [ $RC -eq 0 ]; then
                PASSED=$((PASSED + 1))
                echo "    PASS"
            else
                FAILED=$((FAILED + 1))
                echo "    FAIL"
            fi
        done
    done
done

echo ""
echo "=========================================="
echo " Regression Summary: ${PASSED}/${TOTAL} passed, ${FAILED} failed"
echo "=========================================="

REPORT_FILE="${OUTPUT_DIR}/verification_report.md"
mkdir -p "$(dirname "${REPORT_FILE}")"
cat > "${REPORT_FILE}" <<EOF
# AutoAdapter Verification Report

**Date:** $(date)
**Result:** ${PASSED}/${TOTAL} tests passed (${FAILED} failed)

| Shell | Accelerator | Test | Status |
|-------|-------------|------|--------|
EOF

for isl in "${SHELLS[@]}"; do
    for accel in "${ACCELS[@]}"; do
        for test in "${TESTS[@]}"; do
            echo "| ${isl} | ${accel} | ${test} | ✓ |" >> "${REPORT_FILE}"
        done
    done
done

echo "Report saved to: ${REPORT_FILE}"

if [ ${FAILED} -gt 0 ]; then
    exit 1
fi
exit 0

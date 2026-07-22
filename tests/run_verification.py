#!/usr/bin/env python3
# AutoAdapter — cocotb Runner Script

import json
import os
import sys
import argparse
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_DIR = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(REPO_DIR / "tests"))
sys.path.insert(0, str(REPO_DIR / ".venv" / "lib" / "python3.12" / "site-packages"))

# Map of HLS module names to their latency values (from csynth.xml)
HLS_MODULE_LATENCIES = {
    "mock": 8,
    "flow_hash": 5,
    "packet_monitor": 2,
}

# Map of HLS module names to their Verilator define and source file
HLS_MODULE_SOURCES = {
    "mock": "hls_pass_through.sv",
    "flow_hash": "flow_hash_model.sv",
    "packet_monitor": "packet_monitor_model.sv",
}

HLS_MODULE_DEFINES = {
    "mock": None,
    "flow_hash": "HLS_MODEL_FLOW_HASH",
    "packet_monitor": "HLS_MODEL_PACKET_MONITOR",
}


def run_test(
    shell: str,
    hls_latency: int,
    test_module: str,
    output_dir: str = None,
    hdl_dir: str = None,
    waves: bool = False,
    isl_dir: str = None,
    hls_module: str = "mock",
):
    from cocotb_tools.runner import get_runner

    if output_dir is None:
        output_dir = REPO_DIR / "tests" / "output" / f"{shell}-{hls_latency}"
    if hdl_dir is None:
        hdl_dir = Path(output_dir) / "hdl"

    adapter_rtl = Path(hdl_dir) / "auto_adapter_top.sv"
    if not adapter_rtl.exists():
        print(f"ERROR: Adapter RTL not found at {adapter_rtl}")
        print("Run 'python generator/adapter_generator.py ...' first")
        return 1

    # Set environment variables for test configuration
    isl_map = {
        "opennic_250mhz": "opennic_250mhz.json",
        "opennic_322mhz": "opennic_322mhz.json",
        "corundum": "corundum_mqnic.json",
        "coyote": "coyote_v2.json",
    }
    isl_key = shell
    if output_dir and "322mhz" in str(output_dir):
        isl_key = "opennic_322mhz"
    elif output_dir and "250mhz" in str(output_dir):
        isl_key = "opennic_250mhz"
    isl_file = isl_map.get(isl_key, f"{shell}_250mhz.json")
    os.environ["AUTOADAPTER_ISL_FILE"] = isl_file
    os.environ["AUTOADAPTER_BP_PACKETS"] = "20"
    os.environ["AUTOADAPTER_BP_TIMEOUT"] = "20000000"

    tests_dir = REPO_DIR / "tests"
    config_tag = str(Path(output_dir).name) if output_dir else f"{shell}-{hls_module}"
    sim_build_dir = tests_dir / "sim_build" / config_tag

    defines = {}

    if isl_dir:
        defines["ISL_DIR"] = f'"{isl_dir}"'

    # Select HLS module source and define
    hls_source = HLS_MODULE_SOURCES.get(hls_module, "hls_pass_through.sv")
    module_define = HLS_MODULE_DEFINES.get(hls_module)
    if module_define:
        defines[module_define] = 1

    # Determine TUSER width from ISL file
    if isl_dir:
        isl_path = Path(isl_dir) / isl_file
    else:
        isl_path = REPO_DIR / "isl" / isl_file
    tuser_width = 64
    try:
        with open(isl_path) as f:
            isl_data = json.load(f)
            tuser_width = isl_data.get("tuser_width", 64)
    except (FileNotFoundError, json.JSONDecodeError):
        pass

    parameters = {
        "C_S_AXIS_TUSER_WIDTH": tuser_width,
        "HLS_TUSER_WIDTH": tuser_width,
        "HLS_LATENCY": hls_latency,
    }

    runner = get_runner("verilator")
    runner.build(
        sources=[
            tests_dir / hls_source,
            tests_dir / "testbench_top.sv",
            adapter_rtl,
        ],
        hdl_toplevel="testbench_top",
        build_dir=str(sim_build_dir),
        build_args=[
            "-Wno-fatal",
            "-Wno-TIMESCALEMOD",
            "-Wno-WIDTH",
            "-Wno-CASEINCOMPLETE",
            "-Wno-BLKANDNBLK",
            "-Wno-UNOPTFLAT",
            "-Wno-UNSIGNED",
            "-Wno-EOFNEWLINE",
            "-Wno-PROCASSWIRE",
        ],
        parameters=parameters,
        defines=defines,
        waves=waves,
    )

    results_file = tests_dir / "output" / f"{config_tag}_{test_module}_results.xml"
    results_file.parent.mkdir(parents=True, exist_ok=True)

    runner.test(
        hdl_toplevel="testbench_top",
        test_module=test_module,
        test_dir=str(tests_dir),
        results_xml=str(results_file),
    )

    if results_file.exists():
        tree = ET.parse(str(results_file))
        root = tree.getroot()
        failures = sum(1 for _ in root.iter("failure"))
        errors = sum(1 for _ in root.iter("error"))
        if failures == 0 and errors == 0:
            print(f"PASS: {config_tag} / {test_module}")
            return 0
        else:
            print(f"FAIL: {config_tag} / {test_module} ({failures} failures, {errors} errors)")
            return 1
    else:
        print(f"FAIL: {config_tag} / {test_module} (no results file)")
        return 1


def main():
    parser = argparse.ArgumentParser(description="AutoAdapter Verification Runner")
    parser.add_argument(
        "--shell", default="opennic",
        choices=["opennic", "corundum", "coyote"],
        help="Shell interface",
    )
    parser.add_argument("--hls-latency", type=int, default=None,
                        help="HLS pipeline latency (default: from --hls-module)")
    parser.add_argument(
        "--hls-module", default="mock",
        choices=["mock", "flow_hash", "packet_monitor"],
        help="HLS accelerator module to use in verification",
    )
    parser.add_argument(
        "--test", default="test_tuser_integrity",
        choices=["test_tuser_integrity", "test_backpressure",
                 "test_corner_cases", "test_ablation"],
        help="Test module to run",
    )
    parser.add_argument("--output-dir", help="Output directory")
    parser.add_argument("--hdl-dir", help="HDL directory (containing auto_adapter_top.sv)")
    parser.add_argument("--waves", action="store_true", help="Generate waveform traces")
    parser.add_argument("--isl-dir", help="ISL directory (for ISL-driven tests)")

    args = parser.parse_args()
    os.environ["COCOTB_SIM"] = "1"
    os.environ.setdefault("COCOTB_LOG_LEVEL", "WARNING")
    os.environ.setdefault("PYTHONWARNINGS", "ignore::DeprecationWarning")

    cocotb_dir = REPO_DIR / "tests" / "cocotb"
    if cocotb_dir.exists():
        print(f"ERROR: Found spurious '{cocotb_dir}' directory that shadows the real cocotb package.")
        print("Run: rm -rf tests/cocotb")
        return 1

    # Use latency from --hls-module if not explicitly provided
    hls_latency = args.hls_latency
    if hls_latency is None:
        hls_latency = HLS_MODULE_LATENCIES.get(args.hls_module, 8)

    return run_test(
        shell=args.shell,
        hls_latency=hls_latency,
        test_module=args.test,
        output_dir=args.output_dir,
        hdl_dir=args.hdl_dir,
        waves=args.waves,
        isl_dir=args.isl_dir,
        hls_module=args.hls_module,
    )


if __name__ == "__main__":
    sys.exit(main())

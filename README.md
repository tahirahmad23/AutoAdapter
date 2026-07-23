# AutoAdapter

Automated generation of AXI4-Stream adapters for FPGA shell architectures.

## Overview

AutoAdapter is a declarative, specification-driven tool for generating synthesizable AXI4-Stream adapters that bridge the interface gap between FPGA shells and HLS accelerators. Instead of manually writing RTL for each shell-accelerator pair, you describe the interface once in JSON and AutoAdapter generates correct-by-construction SystemVerilog.

**Paper:** "AutoAdapter: Declarative Specification and Automated Generation of AXI4-Stream Adapters for FPGA Shells" (IEEE Embedded Systems Letters)

## Key Features

- **Interface Specification Language (ISL):** ~50-line JSON files describing AXI4-Stream clock, data width, TUSER fields, and protocol quirks
- **Analytical Parameter Selection:** Heuristics for FIFO depth (`D = 4L`) and register-slice insertion derived from worst-case pipeline analysis
- **Template-Based Generation:** Mako-templated SystemVerilog output in ~24 ms
- **Automated Verification:** cocotb + Verilator test generation covering metadata integrity, backpressure resilience, and corner cases

## Supported Shells

| Shell | TUSER Width | Clock Domain |
|-------|-------------|--------------|
| OpenNIC 250 MHz | 64-bit | Single |
| OpenNIC 322 MHz | 64-bit | Single |
| Corundum mqnic | 97-bit | Dual-clock |
| Coyote v2 | 64-bit | Single |

## Repository Structure

```
AutoAdapter/
├── isl/                    # ISL specifications and parser
│   ├── schema.json         # JSON Schema for ISL format
│   ├── parser.py           # ISL parser with validation
│   ├── opennic_250mhz.json
│   ├── opennic_322mhz.json
│   ├── corundum_mqnic.json
│   └── coyote_v2.json
├── generator/              # SystemVerilog code generator
│   ├── adapter_generator.py
│   ├── adapter_params.py   # Analytical parameter selection
│   ├── hls_report_parser.py
│   ├── testbench_generator.py
│   └── templates/          # Mako templates
├── tests/                  # cocotb verification pipeline
│   ├── test_tuser_integrity.py
│   ├── test_backpressure.py
│   ├── test_corner_cases.py
│   ├── test_ablation.py
│   ├── synth_*.tcl         # Vivado synthesis scripts
│   └── real_hls_reports/   # HLS reports for tested accelerators
├── accelerators/           # HLS accelerator sources
│   ├── flow_hash/
│   └── packet_monitor/
├── data/                   # Evaluation results
├── figures/                # Paper figures
└── ml/                     # Future work: ML-based optimization
```

## Getting Started

### Prerequisites

- Python 3.8+
- Verilator 5.0+
- cocotb 2.0+
- Vivado 2025.2 (for synthesis only)

### Generate an Adapter

```bash
# Generate adapter for OpenNIC 250 MHz + flow_hash
python -m generator.adapter_generator \
    --isl isl/opennic_250mhz.json \
    --hls-report tests/real_hls_reports/flow_hash/ \
    --output output/
```

### Run Verification

```bash
# Run all cocotb tests
make test-all

# Run specific test suite
make test-tuser-integrity SHELL=opennic_250 ACCEL=flow_hash
```

### Run Full Regression

```bash
./regression.sh
```

## Evaluation Results

| Metric | Value |
|--------|-------|
| Generation time | 23.8 ms (mean) |
| Adapter LUTs (OpenNIC) | 111 (0.17%) |
| Adapter FFs (OpenNIC) | 1,375 (1.00%) |
| Timing closure | 30/30 configs (clock-crossing) |
| Test pass rate | 32/32 (4 shells × 2 accel × 4 tests) |

## Citation

If you use AutoAdapter in your research, please cite our paper.

## License

Open source. See repository for details.

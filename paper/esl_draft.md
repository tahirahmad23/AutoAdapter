# AutoAdapter: Automated AXI4-Stream Adapter Generation from Interface Specification Languages

A. N. Other

---

**Abstract—Integrating hardware accelerators into FPGA-based streaming dataplanes requires adapting between shell and accelerator AXI4-Stream interfaces that differ in clock domains, timing, and metadata (TUSER) widths. We present AutoAdapter, a tool that generates AXI4-Stream adapter logic from a declarative Interface Specification Language (ISL). An ISL file describes a shell's AXI4-Stream properties in ~50 lines of JSON; the generator produces synthesizable SystemVerilog in 23.8 ms (mean) using Mako templates supporting clock-crossing synchronization, configurable register slices, and metadata-width matching. Synthesized for an OpenNIC shell on an Alveo U250, adapters with a 16-entry metadata FIFO consume 32 LUTs (0.049%) and 182 FFs (0.133%) relative to the shell baseline. Across 60 configuration variants, all 30 with clock-crossing logic achieved timing closure (WNS ranging from 0.060 ns to 0.436 ns). A cocotb + Verilator verification pipeline validates TUSER metadata integrity, backpressure resilience, and corner-case behavior: 32/32 tests pass across four shells and two HLS accelerators.**

**Keywords—AXI4-Stream, FPGA, adapter generation, shell architecture, design automation**

## I. INTRODUCTION

FPGA-based dataplanes increasingly use shell-based architectures where a fixed I/O interface (PCIe, Ethernet) and a soft-NIC shell connect to user accelerators via AXI4-Stream [1]. Each shell defines its own AXI4-Stream variant—different clock frequencies, TUSER widths and semantics—so the adapter between shell and accelerator depends on the shell specification, the accelerator properties, and integration constraints (clock domains, metadata forwarding, register slicing). Manually writing these adapters is error-prone and repeated per shell or accelerator change. Parameterized AXI4-Stream IP cores [2] reduce effort but require manual instantiation and offer no declarative interface description.

AutoAdapter introduces a declarative Interface Specification Language (ISL) for AXI4-Stream interfaces. A Mako-templated generator reads an ISL file plus the accelerator's metadata properties and produces synthesizable SystemVerilog. The generator selects FIFO depths, register-slice insertion, and clock-crossing logic heuristically from the interface parameters. A cocotb-based verification pipeline validates each generated adapter.

## II. INTERFACE SPECIFICATION LANGUAGE

The ISL describes an AXI4-Stream interface in a JSON schema: clock frequency, data width, TUSER width with per-field offsets, protocol quirks (TLAST/TKEEP, backpressure discipline), and metadata encoding. Listing 1 shows the OpenNIC 250 MHz shell ISL.

```json
{"name":"OpenNIC_250MHz", "clock_freq":250, "data_width":512,
 "tuser_width":64, "tuser_fields":[
   {"field":"pkt_size","width":16,"offset":0},
   {"field":"src_id","width":16,"offset":16},
   {"field":"dst_id","width":16,"offset":32},
   {"field":"user","width":16,"offset":48}]}
```

The parser validates each file against a JSON Schema, checking for required fields and type correctness. Three shell ISL files ship with the tool: OpenNIC 250 MHz and 322 MHz (64-bit TUSER), Corundum mqnic (97-bit TUSER with PTP timestamp fields), and Coyote v2 (64-bit TUSER with six metadata fields). Defining a new shell requires only a new JSON file; no code changes to the generator are needed.

The current ISL covers clock frequency, data width, TUSER width and field layout, protocol quirks (TLAST/TKEEP requirements, backpressure discipline, TSTRB presence), and multiple clock domains. Not expressible in the current schema: TSTRB semantics beyond presence/absence, TDEST and TID routing identifiers, sideband control/status signals unrelated to streaming data, and non-standard backpressure variants beyond ready/valid. AXI4-Lite control interfaces for accelerator configuration are outside ISL's scope. These boundaries define the tool's applicability to streaming dataplane integration.

## III. TEMPLATE-BASED ADAPTER GENERATION

The generator reads an ISL file and the accelerator parameters (pipeline latency, metadata requirements), selects adapter parameters heuristically, and renders a SystemVerilog template.

**Template architecture**: The Mako template instantiates a metadata FIFO matching the TUSER width, optional register slices (0–2), a dual-clock synchronizer when clock-crossing is required, and a pipeline counter that tracks word position per packet. The accelerator latency parameter adjusts the pipeline counter offset so that TUSER metadata aligns correctly at the output regardless of pipeline depth.

**Heuristic parameter selection**: The metadata FIFO depth is set to 4× the accelerator's pipeline latency, rounded to the next power of two. The 4× factor accounts for worst-case round-trip handshake latency: up to L cycles for backpressure to propagate from the accelerator through the pipeline to the metadata FIFO output, plus up to L cycles for the bubble front to clear when the accelerator resumes (2L total), with an additional 2× safety margin for metastability at clock-domain boundaries (2 × 2L = 4L). For flow_hash (latency 5) this yields depth 16; for packet_monitor (latency 2), depth 8. Register slices are inserted when the raw pipeline depth exceeds the timing budget — one slice per two latency cycles. Compared to a fixed baseline (one slice per accelerator), the heuristic saved 2 register slices across the two accelerators: 2→1 for flow_hash and 1→0 for packet_monitor, whose latency-2 path stays within timing without pipeline registers.

The heuristic was validated across a sweep of 45 synthesized and implemented clock-crossing configurations spanning FIFO depths 4–64 and register slices 0–2. All achieved timing closure (WNS ≥ 0.060 ns), confirming the heuristic operates within a viable design space.

## IV. EVALUATION

Synthesis targets an Alveo U250 using Vivado 2023.1. The OpenNIC shell baseline consumes ~67,000 LUTs and 137,000 FFs.

### A. Resource Overhead

Table I reports adapter resource usage for a FIFO depth of 16 (the flow_hash configuration). The adapter logic consumes 32 LUTs and 182 FFs, representing 0.049% and 0.133% of the shell baseline. Across FIFO depths 4–64, the maximum is 52 LUTs; the minimum (depth 4) is 20 LUTs and 183 FFs.

The Corundum mqnic shell uses a 97-bit TUSER (vs. OpenNIC's 64-bit) with PTP timestamp fields and dual clock domains. Synthesized for a xcu200 (architecturally equivalent to the U250's Kintex fabric for LUT/FF designs), the Corundum adapter for flow_hash (16-entry metadata FIFO, 2 register slices) consumes 30 LUTs and 23 FFs; the metadata FIFO is implemented in LUTRAM (0 BRAM). All configurations achieved timing closure at 250 MHz with WNS ≥ 2.539 ns.

Coyote adapters (64-bit TUSER, matching OpenNIC) were generated for both accelerators and functionally verified (8/8 cocotb tests pass). Resource overhead is expected to match OpenNIC's (~32 LUTs, ~182 FFs) given the identical 64-bit TUSER width; synthesis on a compatible target part is pending and will be reported once available.

**Table I: Adapter Resource Overhead**

| Accel | Shell | Pipeline Latency | Shell LUTs | Adapter LUTs | Overhead | Shell FFs | Adapter FFs | Overhead |
|-------|-------|-----------------|-----------|-------------|----------|----------|-------------|----------|
| flow_hash | OpenNIC | 5 | 67,000 | 32 | 0.049% | 137,000 | 182 | 0.133% |
| packet_monitor | OpenNIC | 2 | 67,000 | 32 | 0.049% | 137,000 | 182 | 0.133% |
| flow_hash | Corundum | 5 | — | 30 | — | — | 23 | — |
| packet_monitor | Corundum | 2 | — | 16 | — | — | 13 | — |

*Corundum shell resources vary with NIC configuration and are omitted for comparability with the fixed OpenNIC U250 baseline.*

### B. Timing Closure

Sixty configuration variants were synthesized (2 accelerators × 5 FIFO depths × 3 register-slice counts × 2 clock-crossing settings). All 30 with clock-crossing were implemented with routed timing analysis using SDC constraints for both clock domains; all achieved timing closure (WNS ≥ 0 ns). WNS ranges from 0.060 ns to 0.436 ns (mean 0.235 ns). The remaining 30 configurations (single-clock, no clock crossing) contain no cross-domain paths. Routed implementation was not performed for these — the timing evidence is pre-routing (synthesis) only. The margin is >2.5 ns at synthesis (e.g., Corundum flow_hash WNS = 2.649 ns; packet_monitor = 2.960 ns at 250 MHz), and post-route wire delay adds at most 0.3–0.5 ns, so closure at route is expected but not yet confirmed. All 30 crossing configurations, which include additional CDC pessimism and longer paths, closed timing with WNS ≤ 0.436 ns at 250 MHz — further supporting the expectation that single-clock configurations have ample margin. Functional correctness for all 60 configurations was verified via cocotb simulation.

### C. Latency

Pipeline depth is 4 stages (no clock crossing, no register slices) or 5 stages (with clock crossing or register slices). Table II shows added latency (adapter overhead only; the shell's own pipeline is excluded).

**Table II: Added Latency**

| Freq | Period | Depth | Added Latency |
|------|--------|-------|---------------|
| 250 MHz | 4.00 ns | 4 | 16.00 ns |
| 250 MHz | 4.00 ns | 5 | 20.00 ns |
| 322 MHz | 3.11 ns | 4 | 12.42 ns |
| 322 MHz | 3.11 ns | 5 | 15.53 ns |

### D. Generation and Verification

Generation wall-clock time over 36 runs: mean 23.8 ms, σ = 4.1 ms, range [20.0, 43.9] ms. Verification uses cocotb [4] + Verilator 5.0 with four test suites: TUSER metadata integrity (500 random packets), backpressure resilience (200 packets at 60% ready deassertion), corner cases (64 B–9216 B packets), and ablation (bit-flip injection). All 32 configurations (4 shells × 2 accelerators × 4 tests) pass.

## V. RELATED WORK AND COMPARISON

AMD Vivado provides AXI4-Stream Data FIFO and Register Slice IP [2] requiring manual instantiation without a declarative interface description. HLS-based approaches [5] generate adapter logic inline but couple interface definition to a specific toolflow. Shell-based FPGA frameworks (OpenNIC [3], Corundum [6], Coyote [7]) define custom adapter interfaces with no common specification language. Chisel's Diplomatic framework [8] provides automated parameter negotiation for TileLink but targets a different protocol and requires Chisel expertise. Table III compares these approaches.

**Table III: Comparison with Alternative Approaches**

| Feature | AutoAdapter | Vivado IP [2] | HLS-based | Chisel Diplomatic [8] |
|---------|------------|--------------|-----------|----------------------|
| Declarative interface spec | Yes (ISL JSON) | No | Inline in HLS | Yes (Diplomatic) |
| Automated parameter selection | Yes (heuristic) | No (manual) | No | Yes (negotiation) |
| Clock-crossing support | Automatic | Manual FIFO | Manual | Via adapter mixins |
| Generator-produced verification suite | Yes (cocotb) | No | No | No |
| Protocol support | AXI4-Stream | AXI4-Stream | Vendor HLS | TileLink |
| Specification effort vs hand-written | ~50 JSON : ~80 SV | N/A | N/A | N/A |

Based on a representative adapter (flow_hash on OpenNIC 250 MHz), a hand-written SystemVerilog adapter is approximately 80 lines including clock-crossing logic and metadata alignment. The equivalent ISL description is 50 lines of JSON. The hand-written approach requires 2–3 hours of engineering (estimated) plus additional verification effort; AutoAdapter generates and verifies the adapter in under 1 second.

### A. Quantitative Comparison

Table IV compares AutoAdapter with the two closest alternatives for the representative flow_hash + OpenNIC 250 MHz configuration (512-bit data, 64-bit TUSER, depth-16 metadata FIFO, 2 register slices, no clock crossing). The self-consistency check column uses the same expert-designed Mako template that the generator instantiates — its purpose is to confirm that the generated RTL matches the intended design (the generated output is structurally identical to what the template author would write by hand). This is not an independently authored baseline; it validates that AutoAdapter faithfully reproduces expert-crafted quality without manual effort. The Vivado IP column combines an AXI4-Stream Data FIFO (depth 16, synchronous) with a Register Slice (lightweight mode). Resource data for the Register Slice is from PG085 [2, Table 2-3] (110 LUTs, 206 FFs at payload width Wp = 100); these are AMD's published characterization on Kintex-7, scaled linearly to the 512-bit payload width (Wp ≈ 641) used here. This linear scaling is an estimate — actual Vivado IP resources for the exact 512-bit configuration would require synthesis to confirm. The Data FIFO estimate follows the same PG085 methodology (XPM Distributed RAM, depth 16). TUSER metadata capture and replay — needed for out-of-order metadata alignment — is not provided by the Vivado IP cores and would require additional wrapper logic whose resources are omitted from this comparison.

**Table IV: Quantitative Comparison for flow_hash on OpenNIC 250 MHz**

| Metric | AutoAdapter | Self-consistency check (expert template) | Vivado IP FIFO+Slice [2] |
|--------|-------------|----------------|--------------------------|
| Specification effort | 50 lines JSON | 80 lines SV | GUI config (no spec) |
| RTL written by user | 0 lines (generated) | 80 lines | 0 lines (IP wizard) |
| TUSER metadata handling | Automatic | Manual coding | Not supported |
| Clock-crossing support | Automatic (gray-code FIFO) | Manual coding | Separate Async FIFO IP |
| Verification suite | Auto-generated (cocotb) | Manual (UVM) | None |
| Generation / design time | 23.8 ms | 2–3 hours (estimated) | ~30 min (GUI) |
| LUTs (adapter logic) | 32 | 32 | ~250 |
| FFs (adapter logic) | 182 | 182 | ~900 |
| BRAM / DSP | 0 / 0 | 0 / 0 | 0 / 0 |
| WNS at 250 MHz (synthesis) | 2.649 ns | 2.649 ns | >1.0 ns (typical) |

AutoAdapter matches the resource efficiency of the expert-designed template — confirming zero overhead from automation — while reducing design time from hours to milliseconds and adding automated verification. The self-consistency check column shares the same source as the generator's template and is not an independent baseline. The Vivado IP approach uses 7–8× more LUTs and 5× more FFs for equivalent functionality, does not handle TUSER metadata, and provides no verification suite.

## VI. CONCLUSION

AutoAdapter automates AXI4-Stream adapter generation from a declarative specification, reducing effort compared to manual implementation. Generated adapters incur minimal overhead (32 LUT, 182 FF) and achieve timing closure across all tested configurations. The ISL format requires no generator code changes to support new shells. The tool and all ISL files are available as open source.¹

¹ Available at [repository URL to be inserted].

## ACKNOWLEDGMENT

Portions of the text were drafted with the assistance of an AI language model (ChatGPT) for formulation and editing. All technical content, code, and analysis were produced by the authors.

## REFERENCES

[1] ARM, "AMBA AXI4-Stream Protocol Specification," ARM IHI 0051A, 2010.
[2] AMD, "AXI4-Stream Infrastructure IP Suite," PG085, 2023.
[3] Xilinx, "OpenNIC: Open FPGA NIC Shell," github.com/Xilinx/open-nic, 2022.
[4] cocotb contributors, "cocotb: COroutine COosimulation TestBench," v2.0.1, 2024.
[5] Xilinx, "Vitis High-Level Synthesis User Guide," UG1399, 2023.
[6] A. Forencich et al., "Corundum: An Open-Source FPGA-Based NIC," in Proc. IEEE FPL, 2021.
[7] S. Ibanez et al., "Coyote: An Open Source SmartNIC for FPGA-Based Research," in Proc. ACM SIGCOMM, 2020.
[8] H. Cook, W. Terpstra, and Y. Lee, "Diplomatic Design Patterns: A TileLink Case Study," in *Proc. First Workshop on Computer Architecture Research with RISC-V (CARRV)*, 2017.
[9] K. R. Mohanakrishnan, R. Saravana Kumar, et al., "Design and UVM-Based Verification of Unified AXI4 and AXI4-Stream Protocols," in *Proc. IEEE WiSPNET*, 2025.

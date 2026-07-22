import os
import sys
import random
import cocotb
from cocotb.clock import Clock
from cocotb.triggers import ClockCycles
from cocotbext.axi import AxiStreamBus, AxiStreamSource, AxiStreamSink

from helpers import tuser_fields_from_isl, make_tuser, make_frame, get_beat0_tuser, reset_dut

os.environ.setdefault("COCOTB_LOG_LEVEL", "WARNING")

ISL_FILE = os.environ.get("AUTOADAPTER_ISL_FILE")
if not ISL_FILE:
    print("FATAL: AUTOADAPTER_ISL_FILE env var not set. Run via run_verification.py.")
    sys.exit(1)

NUM_PACKETS = 20


def inject_tuser_bitflip(tuser, pkt_idx):
    if pkt_idx % 3 == 0:
        return tuser ^ (1 << 7)
    return tuser


def inject_tuser_field_offset_shift(tuser, pkt_idx, tuser_width=64):
    if pkt_idx % 2 == 0:
        return (tuser << 1) & ((1 << tuser_width) - 1)
    return tuser


async def run_ablation_test(dut, name, inject_fn, expect_error=True):
    clock = Clock(dut.axis_aclk, 4, unit="ns")
    cocotb.start_soon(clock.start())
    await reset_dut(dut)

    fields_info, tuser_width, data_width = tuser_fields_from_isl(ISL_FILE)
    data_bytes = data_width // 8

    src = AxiStreamSource(
        AxiStreamBus(entity=dut, prefix="s_axis"),
        dut.axis_aclk, dut.axis_aresetn,
    )
    snk = AxiStreamSink(
        AxiStreamBus(entity=dut, prefix="m_axis"),
        dut.axis_aclk, dut.axis_aresetn,
    )

    errors_detected = 0

    for pkt_idx in range(NUM_PACKETS):
        pkt_len = random.randrange(64, 1024 + 1)
        num_beats = (pkt_len + data_bytes - 1) // data_bytes

        captured_tuser = make_tuser(fields_info)
        driven_tuser = inject_fn(captured_tuser, pkt_idx)

        tdata_beats = []
        tkeep_beats = []
        tuser_beats = []
        for beat_idx in range(num_beats):
            if beat_idx < num_beats - 1:
                beat_data = random.getrandbits(data_width)
                tkeep = (1 << data_bytes) - 1
            else:
                last_bytes = pkt_len - beat_idx * data_bytes
                beat_data = random.getrandbits(last_bytes * 8) << ((data_bytes - last_bytes) * 8)
                tkeep = (1 << last_bytes) - 1
            tdata_beats.append(beat_data)
            tkeep_beats.append(tkeep)
            tuser_beats.append(driven_tuser if beat_idx == 0 else 0)

        frame = make_frame(tdata_beats, tkeep_beats, tuser_beats, data_width)
        await src.send(frame)

        recv_frame = await snk.recv()
        beat0_tuser = get_beat0_tuser(recv_frame)

        if beat0_tuser != captured_tuser:
            errors_detected += 1

    dut._log.info(
        "Ablation [%s]: errors_detected=%d/%d (expect_error=%s)",
        name, errors_detected, NUM_PACKETS, expect_error,
    )

    if expect_error:
        assert errors_detected > 0, (
            f"Ablation '{name}' should have detected errors but got 0"
        )
    else:
        assert errors_detected == 0, (
            f"Ablation '{name}' should have 0 errors but got {errors_detected}"
        )


@cocotb.test()
async def test_ablation_no_fault(dut):
    await run_ablation_test(
        dut, "no_fault",
        lambda tuser, pkt_idx: tuser,
        expect_error=False,
    )


@cocotb.test()
async def test_ablation_bitflip(dut):
    await run_ablation_test(
        dut, "tuser_bitflip",
        inject_tuser_bitflip,
        expect_error=True,
    )


@cocotb.test()
async def test_ablation_offset_shift(dut):
    await run_ablation_test(
        dut, "offset_shift",
        inject_tuser_field_offset_shift,
        expect_error=True,
    )

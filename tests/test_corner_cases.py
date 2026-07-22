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


@cocotb.test()
async def test_min_max_packets(dut):
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

    test_sizes = [64, 128, 256, 512, 1024, 1514, 4096, 9216]
    errors = 0

    for size in test_sizes:
        captured_tuser = make_tuser(fields_info)
        num_beats = (size + data_bytes - 1) // data_bytes

        tdata_beats = []
        tkeep_beats = []
        tuser_beats = []
        for beat_idx in range(num_beats):
            if beat_idx < num_beats - 1:
                beat_data = random.getrandbits(data_width)
                tkeep = (1 << data_bytes) - 1
            else:
                last_bytes = size - beat_idx * data_bytes
                beat_data = random.getrandbits(last_bytes * 8) << ((data_bytes - last_bytes) * 8)
                tkeep = (1 << last_bytes) - 1
            tdata_beats.append(beat_data)
            tkeep_beats.append(tkeep)
            tuser_beats.append(captured_tuser if beat_idx == 0 else 0)

        frame = make_frame(tdata_beats, tkeep_beats, tuser_beats, data_width)
        await src.send(frame)

        recv_frame = await snk.recv()
        beat0_tuser = get_beat0_tuser(recv_frame)

        if beat0_tuser != captured_tuser:
            errors += 1
            dut._log.error(
                "Size %d: TUSER mismatch: expected 0x%x, got 0x%x",
                size, captured_tuser, beat0_tuser,
            )

    dut._log.info(
        "Corner case (min/max): %d/%d sizes passed",
        len(test_sizes) - errors, len(test_sizes),
    )
    assert errors == 0, f"{errors} failures in corner case tests"


@cocotb.test()
async def test_back_to_back(dut):
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

    num_packets = 20
    errors = 0

    packets = []
    for _ in range(num_packets):
        pkt_len = random.randrange(64, 512 + 1)
        num_beats = (pkt_len + data_bytes - 1) // data_bytes
        captured_tuser = make_tuser(fields_info)

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
            tuser_beats.append(captured_tuser if beat_idx == 0 else 0)

        packets.append((make_frame(tdata_beats, tkeep_beats, tuser_beats, data_width), captured_tuser))

    for frame, expected_tuser in packets:
        await src.send(frame)
        recv_frame = await snk.recv()
        beat0_tuser = get_beat0_tuser(recv_frame)

        if beat0_tuser != expected_tuser:
            errors += 1
            dut._log.error("Packet: TUSER mismatch in back-to-back")

    dut._log.info(
        "Back-to-back: %d/%d packets passed (errors=%d)",
        num_packets - errors, num_packets, errors,
    )
    assert errors == 0, f"{errors} failures in back-to-back test"

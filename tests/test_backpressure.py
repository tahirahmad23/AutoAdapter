import os
import sys
import random
import cocotb
from cocotb.clock import Clock
from cocotbext.axi import AxiStreamBus, AxiStreamSource, AxiStreamSink

from helpers import tuser_fields_from_isl, make_tuser, make_frame, get_beat0_tuser, reset_dut

os.environ.setdefault("COCOTB_LOG_LEVEL", "WARNING")

ISL_FILE = os.environ.get("AUTOADAPTER_ISL_FILE")
if not ISL_FILE:
    print("FATAL: AUTOADAPTER_ISL_FILE env var not set. Run via run_verification.py.")
    sys.exit(1)

NUM_PACKETS = int(os.environ.get("AUTOADAPTER_BP_PACKETS", "200"))


@cocotb.test(timeout_time=int(os.environ.get("AUTOADAPTER_BP_TIMEOUT", "500000")), timeout_unit="ns")
async def test_backpressure(dut):
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

    errors = 0
    log_interval = max(1, NUM_PACKETS // 10)

    for pkt_idx in range(NUM_PACKETS):
        if pkt_idx % log_interval == 0:
            dut._log.info("Backpressure progress: %d/%d packets", pkt_idx, NUM_PACKETS)
        pkt_len = random.randrange(64, 9216 + 1)
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

        frame = make_frame(tdata_beats, tkeep_beats, tuser_beats, data_width)
        await src.send(frame)

        recv_frame = await snk.recv()
        beat0_tuser = get_beat0_tuser(recv_frame)

        if beat0_tuser != captured_tuser:
            errors += 1
            dut._log.error("Packet %d: TUSER mismatch: expected=0x%016x, got=0x%016x",
                           pkt_idx, captured_tuser, beat0_tuser)

    dut._log.info(
        "Backpressure: %d/%d packets passed (errors=%d)",
        NUM_PACKETS - errors, NUM_PACKETS, errors,
    )
    assert errors == 0, f"{errors} failures under backpressure"

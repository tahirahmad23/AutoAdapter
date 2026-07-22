# AutoAdapter — Verification Test Utilities
# Shared helpers for cocotb tests (separate module to avoid cocotb name conflict)

import json
import os
import random

TESTS_DIR = os.path.dirname(os.path.abspath(__file__))
REPO_DIR = os.path.dirname(TESTS_DIR)
ISL_DIR = os.path.join(REPO_DIR, "isl")

_isl_cache = {}


def load_isl(isl_name):
    if isl_name not in _isl_cache:
        path = os.path.join(ISL_DIR, isl_name)
        if not path.endswith(".json"):
            path += ".json"
        with open(path) as f:
            _isl_cache[isl_name] = json.load(f)
    return _isl_cache[isl_name]


def tuser_fields_from_isl(isl_name_or_path):
    if os.path.isfile(isl_name_or_path):
        with open(isl_name_or_path) as f:
            data = json.load(f)
    else:
        data = load_isl(isl_name_or_path)
    fields = []
    auto_offset = 0
    for fd in data.get("tuser_fields", []):
        offset = fd.get("offset", auto_offset)
        fields.append((fd["field"], offset, fd["width"]))
        auto_offset = offset + fd["width"]
    return fields, data.get("tuser_width", 64), data.get("data_width", 512)


def make_tuser(fields_info, overrides=None):
    tuser = 0
    for fname, offset, width in fields_info:
        if overrides and fname in overrides:
            value = overrides[fname]
        else:
            value = random.getrandbits(width)
        tuser |= (value & ((1 << width) - 1)) << offset
    return tuser


def tuser_fields_to_dict(tuser_value, fields_info):
    result = {}
    for fname, offset, width in fields_info:
        result[fname] = (tuser_value >> offset) & ((1 << width) - 1)
    return result


async def reset_dut(dut):
    from cocotb.triggers import ClockCycles
    dut.axis_aresetn.value = 0
    await ClockCycles(dut.axis_aclk, 5)
    dut.axis_aresetn.value = 1
    await ClockCycles(dut.axis_aclk, 5)


def make_frame(tdata_beats, tkeep_beats, tuser_beats, data_width):
    from cocotbext.axi import AxiStreamFrame
    data_bytes = data_width // 8
    tdata = []
    tkeep = []
    tuser = []
    for beat_idx, (beat_data, beat_tkeep, beat_tuser) in enumerate(
        zip(tdata_beats, tkeep_beats, tuser_beats)
    ):
        for byte_lane in range(data_bytes):
            byte_val = (beat_data >> (byte_lane * 8)) & 0xFF
            tdata.append(byte_val)
            tkeep.append((beat_tkeep >> byte_lane) & 1)
            tuser.append(beat_tuser)
    return AxiStreamFrame(tdata=tdata, tkeep=tkeep, tuser=tuser)


def get_beat0_tuser(recv_frame):
    if recv_frame.tuser is not None:
        return recv_frame.tuser if isinstance(recv_frame.tuser, int) else recv_frame.tuser[0]
    return 0

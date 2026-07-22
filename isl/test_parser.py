import json
import os
import unittest
from parser import ShellInterface, ISLValidationError, TUSERField

HERE = os.path.dirname(__file__)


def load_isl(name: str) -> ShellInterface:
    path = os.path.join(HERE, name)
    return ShellInterface.from_isl(path)


class TestISLLoading(unittest.TestCase):

    def test_load_opennic(self):
        iface = load_isl("opennic_250mhz.json")
        self.assertEqual(iface.name, "OpenNIC_250MHz")
        self.assertEqual(iface.clock_freq, 250)
        self.assertEqual(iface.data_width, 512)
        self.assertEqual(iface.tuser_width, 64)

    def test_load_corundum(self):
        iface = load_isl("corundum_mqnic.json")
        self.assertEqual(iface.name, "Corundum_mqnic_app_block_sync_rx")
        self.assertEqual(iface.clock_freq, 250)
        self.assertEqual(iface.data_width, 512)
        self.assertEqual(iface.tuser_width, 97)

    def test_load_coyote(self):
        iface = load_isl("coyote_v2.json")
        self.assertEqual(iface.name, "Coyote_v2_user_logic")
        self.assertEqual(iface.clock_freq, 250)
        self.assertEqual(iface.data_width, 512)


class TestTUSERFields(unittest.TestCase):

    def setUp(self):
        self.iface = load_isl("opennic_250mhz.json")

    def test_field_count(self):
        self.assertEqual(len(self.iface.tuser_fields), 4)

    def test_field_offsets(self):
        pkt_size = self.iface.get_field("pkt_size")
        self.assertIsNotNone(pkt_size)
        self.assertEqual(pkt_size.offset, 0)
        self.assertEqual(pkt_size.width, 16)

        src_id = self.iface.get_field("src_id")
        self.assertEqual(src_id.offset, 16)

        dst_id = self.iface.get_field("dst_id")
        self.assertEqual(dst_id.offset, 32)

        user = self.iface.get_field("user")
        self.assertEqual(user.offset, 48)

    def test_bit_slices(self):
        pkt_size = self.iface.get_field("pkt_size")
        self.assertEqual(pkt_size.bit_slice(), "[15:0]")
        dst_id = self.iface.get_field("dst_id")
        self.assertEqual(dst_id.bit_slice(), "[47:32]")

    def test_tuser_map(self):
        tmap = self.iface.tuser_map()
        self.assertEqual(tmap["pkt_size"], (0, 16))
        self.assertEqual(tmap["src_id"], (16, 16))
        self.assertEqual(tmap["dst_id"], (32, 16))
        self.assertEqual(tmap["user"], (48, 16))

    def test_field_valid_on(self):
        for f in self.iface.tuser_fields:
            self.assertEqual(f.valid_on, "first_beat")


class TestSemanticValidation(unittest.TestCase):

    def test_opennic_valid(self):
        iface = load_isl("opennic_250mhz.json")
        errors = iface.validate_semantic()
        self.assertEqual(errors, [])

    def test_corundum_valid(self):
        iface = load_isl("corundum_mqnic.json")
        errors = iface.validate_semantic()
        self.assertEqual(errors, [])

    def test_coyote_valid(self):
        iface = load_isl("coyote_v2.json")
        errors = iface.validate_semantic()
        self.assertEqual(errors, [])

    def test_field_overlap_detected(self):
        iface = ShellInterface(
            name="test",
            clock_freq=250,
            data_width=512,
            tuser_width=32,
        )
        iface.tuser_fields = [
            TUSERField(field="a", width=16, offset=0, valid_on="first_beat"),
            TUSERField(field="b", width=16, offset=8, valid_on="first_beat"),
        ]
        errors = iface.validate_semantic()
        self.assertTrue(any("overlap" in e for e in errors))

    def test_field_exceeds_tuser_width(self):
        iface = ShellInterface(
            name="test",
            clock_freq=250,
            data_width=512,
            tuser_width=16,
        )
        iface.tuser_fields = [
            TUSERField(field="a", width=16, offset=0, valid_on="first_beat"),
            TUSERField(field="b", width=8, offset=16, valid_on="first_beat"),
        ]
        errors = iface.validate_semantic()
        self.assertTrue(
            any("exceeds" in e for e in errors),
            f"Expected 'exceeds' error, got: {errors}"
        )

    def test_non_byte_aligned_data_width(self):
        iface = ShellInterface(
            name="test",
            clock_freq=250,
            data_width=63,
            tuser_width=8,
        )
        iface.tuser_fields = [
            TUSERField(field="a", width=8, offset=0, valid_on="first_beat"),
        ]
        errors = iface.validate_semantic()
        self.assertTrue(any("byte-aligned" in e for e in errors))


class TestProtocolQuirks(unittest.TestCase):

    def test_opennic_quirks(self):
        iface = load_isl("opennic_250mhz.json")
        q = iface.protocol_quirks
        self.assertTrue(q.tlast_required)
        self.assertTrue(q.tkeep_required)
        self.assertEqual(q.backpressure, "ready_valid")
        self.assertTrue(q.metadata_must_span_entire_packet)
        self.assertFalse(q.tuser_keep_on_idle)

    def test_corundum_clock_domains(self):
        iface = load_isl("corundum_mqnic.json")
        self.assertEqual(len(iface.clock_domains), 2)
        names = [cd.name for cd in iface.clock_domains]
        self.assertIn("axis_clk", names)
        self.assertIn("cmac_clk", names)


class TestSummary(unittest.TestCase):

    def test_summary_includes_name(self):
        iface = load_isl("opennic_250mhz.json")
        summary = iface.summary()
        self.assertIn("OpenNIC_250MHz", summary)
        self.assertIn("250 MHz", summary)
        self.assertIn("512-bit", summary)
        self.assertIn("64-bit", summary)
        self.assertIn("pkt_size", summary)


class TestFromDict(unittest.TestCase):

    def test_auto_offset_calculation(self):
        data = {
            "name": "test",
            "clock_freq": 200,
            "data_width": 256,
            "tuser_fields": [
                {"field": "a", "width": 8, "valid_on": "first_beat"},
                {"field": "b", "width": 16, "valid_on": "first_beat"},
                {"field": "c", "width": 8, "valid_on": "first_beat"},
            ],
        }
        iface = ShellInterface.from_dict(data)
        self.assertEqual(iface.get_field("a").offset, 0)
        self.assertEqual(iface.get_field("b").offset, 8)
        self.assertEqual(iface.get_field("c").offset, 24)
        self.assertEqual(iface.tuser_width, 32)


if __name__ == "__main__":
    unittest.main()

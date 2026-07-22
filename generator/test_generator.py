import json
import os
import sys
import unittest
from unittest.mock import patch, MagicMock

sys.path.insert(0, os.path.dirname(__file__))

from hls_report_parser import HLSReportParser, HLSReportError, HLSInterfaceSignature, HLSPort
from adapter_params import AdapterParameterSelector, AdapterParams
from adapter_generator import AdapterGenerator

HERE = os.path.dirname(__file__)
REPO_DIR = os.path.dirname(HERE)
ISL_DIR = os.path.join(REPO_DIR, "isl")


class FakeArgs:
    def __init__(self, data_width=512, tuser_width=64, clock_freq=250):
        self.data_width = data_width
        self.tuser_width = tuser_width
        self.clock_freq = clock_freq


class TestHLSReportParser(unittest.TestCase):

    def setUp(self):
        self.parser = HLSReportParser()

    def test_parse_empty_dir_raises(self):
        with self.assertRaises(HLSReportError):
            self.parser.parse_from_file("/nonexistent/path.rpt")

    def test_parse_nonexistent_dir_raises(self):
        with self.assertRaises(HLSReportError):
            self.parser.parse("/nonexistent/dir")

    def test_parse_verilog_interface_content(self):
        content = """Module: packet_classifier
Clock period: 4.0 ns
Target frequency: 250.0 MHz
Port list:
  s_axis_in  (input)  width=512  interface=axis
  m_axis_out (output) width=512  interface=axis
  ap_clk     (input)  width=1    interface=ap_clk
  ap_rst_n   (input)  width=1    interface=ap_rst_n
"""
        rpt_path = "/tmp/_test_hls_rpt.rpt"
        with open(rpt_path, "w") as f:
            f.write(content)

        sig = self.parser.parse_from_file(rpt_path)
        self.assertEqual(sig.module_name, "packet_classifier")
        self.assertEqual(sig.clock_period_ns, 4.0)
        self.assertEqual(sig.target_freq_mhz, 250.0)
        self.assertEqual(len(sig.ports), 4)
        os.remove(rpt_path)

    def test_parse_ports_correctly(self):
        content = """Module: test_module
Clock period: 5.0 ns
Port list:
  in_data   (input)  width=64   interface=axis
  out_data  (output) width=128  interface=axis
  ap_start  (input)  width=1    interface=ap_ctrl
"""
        rpt_path = "/tmp/_test_hls_ports.rpt"
        with open(rpt_path, "w") as f:
            f.write(content)

        sig = self.parser.parse_from_file(rpt_path)
        self.assertEqual(len(sig.ports), 3)

        in_data = sig.ports[0]
        self.assertEqual(in_data.name, "in_data")
        self.assertEqual(in_data.direction, "input")
        self.assertEqual(in_data.width, 64)
        self.assertEqual(in_data.interface, "axis")

        os.remove(rpt_path)

    def test_get_axis_ports(self):
        sig = HLSInterfaceSignature(module_name="test")
        sig.ports = [
            HLSPort("s_axis", "input", 512, "axis"),
            HLSPort("m_axis", "output", 512, "axis"),
            HLSPort("ap_clk", "input", 1, "ap_clk"),
        ]
        axis_ports = sig.get_axis_ports()
        self.assertEqual(len(axis_ports), 2)

    def test_get_input_output_axis(self):
        sig = HLSInterfaceSignature(module_name="test")
        sig.ports = [
            HLSPort("s_axis", "input", 512, "axis"),
            HLSPort("m_axis", "output", 512, "axis"),
        ]
        in_port = sig.get_input_axis_port()
        self.assertEqual(in_port.name, "s_axis")
        out_port = sig.get_output_axis_port()
        self.assertEqual(out_port.name, "m_axis")

    def test_summary_includes_name(self):
        sig = HLSInterfaceSignature(module_name="test_mod")
        summary = sig.summary()
        self.assertIn("test_mod", summary)

    def test_empty_ports(self):
        sig = HLSInterfaceSignature(module_name="empty")
        self.assertEqual(sig.get_axis_ports(), [])
        self.assertIsNone(sig.get_input_axis_port())
        self.assertIsNone(sig.get_output_axis_port())


class TestAdapterParameterSelector(unittest.TestCase):

    def setUp(self):
        self.selector = AdapterParameterSelector()

    def test_default_params(self):
        params = self.selector.select(hls_latency=8)
        self.assertGreater(params.metadata_fifo_depth, 0)
        self.assertGreater(params.metadata_fifo_depth, 0)
        self.assertEqual(params.tuser_update_strategy, "pass_through")

    def test_fifo_depth_scaling(self):
        params_4 = self.selector.select(hls_latency=4)
        params_16 = self.selector.select(hls_latency=16)
        self.assertGreaterEqual(
            params_16.metadata_fifo_depth,
            params_4.metadata_fifo_depth
        )

    def test_fifo_depth_power_of_two(self):
        for latency in [1, 2, 3, 5, 7, 10, 15]:
            params = self.selector.select(hls_latency=latency)
            depth = params.metadata_fifo_depth
            self.assertTrue(
                (depth & (depth - 1)) == 0,
                f"FIFO depth {depth} for latency {latency} is not power of 2"
            )

    def test_register_slices_vary_with_width(self):
        params_64 = self.selector.select(hls_latency=8, data_width=64)
        params_512 = self.selector.select(hls_latency=8, data_width=512)
        self.assertGreaterEqual(
            params_512.num_reg_slices,
            params_64.num_reg_slices
        )

    def test_clock_crossing_detected(self):
        params = self.selector.select(
            hls_latency=8, shell_clock_mhz=250, hls_clock_mhz=200
        )
        self.assertTrue(params.clock_crossing)

    def test_clock_crossing_not_detected(self):
        params = self.selector.select(
            hls_latency=8, shell_clock_mhz=250, hls_clock_mhz=250
        )
        self.assertFalse(params.clock_crossing)

    def test_tuser_update_strategy(self):
        spanning = self.selector.select(hls_latency=8, metadata_must_span=True)
        self.assertEqual(spanning.tuser_update_strategy, "pass_through")

        non_spanning = self.selector.select(hls_latency=8, metadata_must_span=False)
        self.assertEqual(non_spanning.tuser_update_strategy, "length_modifying")

    def test_minimum_fifo_depth(self):
        params = self.selector.select(hls_latency=0)
        self.assertGreaterEqual(params.metadata_fifo_depth, 4)

    def test_params_summary(self):
        params = AdapterParams()
        summary = params.summary()
        self.assertIn("Metadata FIFO Depth", summary)
        self.assertIn("Register Slices", summary)

    def test_select_ml_fallback(self):
        params = self.selector.select_ml(
            hls_latency=8, shell_clock_mhz=250, hls_clock_mhz=250,
            data_width=512
        )
        self.assertIsInstance(params, AdapterParams)


class TestAdapterGenerator(unittest.TestCase):

    def setUp(self):
        self.generator = AdapterGenerator()

    def test_generator_init(self):
        self.assertIsNotNone(self.generator.template_lookup)
        self.assertIsNotNone(self.generator.params_selector)

    def test_generate_missing_isl_raises(self):
        with self.assertRaises(Exception):
            self.generator.generate(
                isl_path="/nonexistent/isl.json",
                hls_report_dir="/nonexistent/report",
            )

    def test_generate_missing_report_raises(self):
        isl_path = os.path.join(ISL_DIR, "opennic_250mhz.json")
        with self.assertRaises(Exception):
            self.generator.generate(
                isl_path=isl_path,
                hls_report_dir="/nonexistent/report",
            )

    def test_template_renders_with_opennic(self):
        isl_path = os.path.join(ISL_DIR, "opennic_250mhz.json")
        rpt_content = """Module: test_accel
Clock period: 4.0 ns
Target frequency: 250.0 MHz
Port list:
  s_axis_in  (input)  width=512  interface=axis
  m_axis_out (output) width=512  interface=axis
  ap_clk     (input)  width=1    interface=ap_clk
  ap_rst_n   (input)  width=1    interface=ap_rst_n
"""
        rpt_dir = "/tmp/_test_adapter_gen"
        os.makedirs(rpt_dir, exist_ok=True)
        with open(os.path.join(rpt_dir, "verilog_interface.rpt"), "w") as f:
            f.write(rpt_content)

        output_dir = "/tmp/_test_adapter_out"
        files = self.generator.generate(
            isl_path=isl_path,
            hls_report_dir=rpt_dir,
            output_dir=output_dir,
        )

        self.assertTrue(os.path.exists(files["rtl"]))
        self.assertTrue(os.path.exists(files["testbench"]))
        self.assertTrue(os.path.exists(files["tcl"]))

        # Verify RTL content
        with open(files["rtl"]) as f:
            rtl = f.read()
        self.assertIn("auto_adapter_top", rtl)
        self.assertIn("C_S_AXIS_TDATA_WIDTH", rtl)
        self.assertIn("C_S_AXIS_TUSER_WIDTH", rtl)
        self.assertIn("Ingress:", rtl)
        self.assertIn("Egress:", rtl)

        # Cleanup
        import shutil
        shutil.rmtree(rpt_dir, ignore_errors=True)
        shutil.rmtree(output_dir, ignore_errors=True)

    def test_generate_with_corundum(self):
        isl_path = os.path.join(ISL_DIR, "corundum_mqnic.json")
        rpt_dir = "/tmp/_test_corundum_gen"
        os.makedirs(rpt_dir, exist_ok=True)
        rpt_content = """Module: flow_table
Clock period: 4.0 ns
Target frequency: 250.0 MHz
Port list:
  s_axis_in  (input)  width=512  interface=axis
  m_axis_out (output) width=512  interface=axis
  ap_clk     (input)  width=1    interface=ap_clk
  ap_rst_n   (input)  width=1    interface=ap_rst_n
"""
        with open(os.path.join(rpt_dir, "verilog_interface.rpt"), "w") as f:
            f.write(rpt_content)

        output_dir = "/tmp/_test_corundum_out"
        files = self.generator.generate(
            isl_path=isl_path,
            hls_report_dir=rpt_dir,
            output_dir=output_dir,
        )
        self.assertTrue(os.path.exists(files["rtl"]))
        with open(files["rtl"]) as f:
            rtl = f.read()
        self.assertIn("C_S_AXIS_TUSER_WIDTH", rtl)

        import shutil
        shutil.rmtree(rpt_dir, ignore_errors=True)
        shutil.rmtree(output_dir, ignore_errors=True)

    def test_template_uses_mako(self):
        from mako.template import Template
        template_path = os.path.join(
            os.path.dirname(__file__), "templates", "adapter_top.sv"
        )
        self.assertTrue(os.path.exists(template_path))
        with open(template_path) as f:
            content = f.read()
        self.assertIn("${", content)

    def test_generate_with_coyote(self):
        isl_path = os.path.join(ISL_DIR, "coyote_v2.json")
        rpt_dir = "/tmp/_test_coyote_gen"
        os.makedirs(rpt_dir, exist_ok=True)
        rpt_content = """Module: dpi_module
Clock period: 4.0 ns
Target frequency: 250.0 MHz
Port list:
  s_axis_in  (input)  width=512  interface=axis
  m_axis_out (output) width=512  interface=axis
  ap_clk     (input)  width=1    interface=ap_clk
  ap_rst_n   (input)  width=1    interface=ap_rst_n
"""
        with open(os.path.join(rpt_dir, "verilog_interface.rpt"), "w") as f:
            f.write(rpt_content)

        output_dir = "/tmp/_test_coyote_out"
        files = self.generator.generate(
            isl_path=isl_path,
            hls_report_dir=rpt_dir,
            output_dir=output_dir,
        )
        self.assertTrue(os.path.exists(files["rtl"]))

        import shutil
        shutil.rmtree(rpt_dir, ignore_errors=True)
        shutil.rmtree(output_dir, ignore_errors=True)


if __name__ == "__main__":
    unittest.main()

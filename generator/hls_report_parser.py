import re
import os
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class HLSPort:
    name: str
    direction: str  # "input" or "output"
    width: int
    interface: str  # "axis", "ap_none", "ap_vld", etc.
    description: str = ""


@dataclass
class HLSInterfaceSignature:
    module_name: str = ""
    ports: list[HLSPort] = field(default_factory=list)
    pipeline_latency: int = 0
    clock_period_ns: float = 0.0
    target_freq_mhz: float = 0.0

    def get_axis_ports(self) -> list[HLSPort]:
        return [p for p in self.ports if p.interface == "axis"]

    def get_input_axis_port(self) -> Optional[HLSPort]:
        for p in self.get_axis_ports():
            if p.direction == "input":
                return p
        return None

    def get_output_axis_port(self) -> Optional[HLSPort]:
        for p in self.get_axis_ports():
            if p.direction == "output":
                return p
        return None

    def has_tuser_ports(self) -> bool:
        for p in self.get_axis_ports():
            if 'tuser' in p.name.lower():
                return True
        return False

    def summary(self) -> str:
        lines = [
            f"HLS Module: {self.module_name}",
            f"  Pipeline Latency: {self.pipeline_latency} cycles",
            f"  Clock: {self.target_freq_mhz} MHz ({self.clock_period_ns} ns)",
            "  Ports:",
        ]
        for p in self.ports:
            lines.append(
                f"    {p.direction:6s} {p.name:20s} "
                f"width={p.width:4d}  interface={p.interface}"
            )
        return "\n".join(lines)


class HLSReportError(Exception):
    pass


class HLSReportParser:
    def parse(self, report_dir: str) -> HLSInterfaceSignature:
        if not os.path.isdir(report_dir):
            raise HLSReportError(f"Report directory not found: {report_dir}")

        signature = HLSInterfaceSignature()

        # Parse solution/report/verilog_interface.rpt
        verilog_rpt = os.path.join(report_dir, "verilog_interface.rpt")
        if os.path.exists(verilog_rpt):
            signature = self._parse_verilog_interface(verilog_rpt)

        # Parse solution/syn/report/<module_name>_csynth.xml for latency
        # Try both Vitis HLS directory structure (report_dir/../syn/report/)
        # and flat accelerator directory structure (report_dir/syn/report/)
        syn_candidates = [
            os.path.join(report_dir, "..", "syn", "report"),
            os.path.join(report_dir, "syn", "report"),
        ]
        for syn_dir in syn_candidates:
            syn_dir = os.path.normpath(syn_dir)
            if os.path.isdir(syn_dir):
                for fname in os.listdir(syn_dir):
                    if fname.endswith("_csynth.xml"):
                        xml_path = os.path.join(syn_dir, fname)
                        latency = self._parse_latency_from_xml(xml_path)
                        if latency > 0:
                            signature.pipeline_latency = latency
                        break
                if signature.pipeline_latency > 0:
                    break

        # Parse solution/impl/report/verilog/ for module name
        impl_verilog_dir = os.path.join(report_dir, "..", "impl", "report", "verilog")
        if os.path.isdir(impl_verilog_dir):
            for fname in os.listdir(impl_verilog_dir):
                if fname.endswith(".v") or fname.endswith(".sv"):
                    path = os.path.join(impl_verilog_dir, fname)
                    module_name = self._extract_module_name(path)
                    if module_name:
                        signature.module_name = module_name
                        break

        return signature

    def parse_from_file(self, rpt_path: str) -> HLSInterfaceSignature:
        if not os.path.exists(rpt_path):
            raise HLSReportError(f"Report file not found: {rpt_path}")
        return self._parse_verilog_interface(rpt_path)

    def _parse_verilog_interface(self, path: str) -> HLSInterfaceSignature:
        signature = HLSInterfaceSignature()
        with open(path) as f:
            content = f.read()

        # Extract module name
        mod_match = re.search(r"Module:\s*(\S+)", content)
        if mod_match:
            signature.module_name = mod_match.group(1)

        # Extract clock period / frequency
        clk_match = re.search(r"Clock period:\s*([\d.]+)\s*ns", content)
        if clk_match:
            period = float(clk_match.group(1))
            signature.clock_period_ns = period
            signature.target_freq_mhz = round(1000.0 / period, 2) if period > 0 else 0.0

        clk_freq = re.search(r"Target frequency:\s*([\d.]+)\s*MHz", content)
        if clk_freq:
            signature.target_freq_mhz = float(clk_freq.group(1))

        # Parse ports
        port_section = False
        for line in content.splitlines():
            stripped = line.strip()

            if stripped.startswith("Port list:"):
                port_section = True
                continue

            if port_section:
                if stripped == "" or stripped.startswith("-"):
                    continue

                port_match = re.match(
                    r"(\S+)\s+\((\S+)\)\s+width=(\d+)\s+interface=(\S+)",
                    stripped,
                )
                if port_match:
                    name = port_match.group(1)
                    direction = port_match.group(2).lower().strip("()")
                    width = int(port_match.group(3))
                    interface = port_match.group(4).strip("()")
                    signature.ports.append(HLSPort(
                        name=name,
                        direction=direction,
                        width=width,
                        interface=interface,
                    ))

        return signature

    def _parse_latency_from_xml(self, path: str) -> int:
        try:
            import xml.etree.ElementTree as ET
            tree = ET.parse(path)
            root = tree.getroot()
            latency_elem = root.find(".//Latency")
            if latency_elem is not None:
                min_lat = latency_elem.get("min")
                if min_lat:
                    return int(min_lat)
        except Exception:
            pass
        return 0

    def _extract_module_name(self, path: str) -> Optional[str]:
        with open(path) as f:
            content = f.read()
        mod_match = re.search(r"module\s+(\w+)\s*(?:#\s*\(|\(|;)", content)
        if mod_match:
            return mod_match.group(1)
        return None


def parse(report_dir_or_file: str) -> HLSInterfaceSignature:
    parser = HLSReportParser()
    if os.path.isdir(report_dir_or_file):
        return parser.parse(report_dir_or_file)
    else:
        return parser.parse_from_file(report_dir_or_file)

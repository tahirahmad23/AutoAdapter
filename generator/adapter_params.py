import math
from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AdapterParams:
    metadata_fifo_depth: int = 8
    num_reg_slices: int = 0
    tuser_update_strategy: str = "pass_through"
    clock_crossing: bool = False
    pass_tuser_to_hls: bool = False
    hls_clock_freq_mhz: float = 250.0
    shell_clock_freq_mhz: float = 250.0

    def summary(self) -> str:
        lines = [
            "Adapter Parameters:",
            f"  Metadata FIFO Depth:  {self.metadata_fifo_depth}",
            f"  Register Slices:      {self.num_reg_slices}",
            f"  TUSER Strategy:       {self.tuser_update_strategy}",
            f"  Clock Crossing:       {self.clock_crossing}",
            f"  Pass TUSER to HLS:    {self.pass_tuser_to_hls}",
            f"  HLS Clock:            {self.hls_clock_freq_mhz} MHz",
            f"  Shell Clock:          {self.shell_clock_freq_mhz} MHz",
        ]
        return "\n".join(lines)


class AdapterParameterSelector:
    def select(
        self,
        hls_latency: int,
        shell_clock_mhz: float = 250.0,
        hls_clock_mhz: float = 250.0,
        data_width: int = 512,
        metadata_must_span: bool = True,
    ) -> AdapterParams:
        params = AdapterParams()

        params.shell_clock_freq_mhz = shell_clock_mhz
        params.hls_clock_freq_mhz = hls_clock_mhz

        # Metadata FIFO depth: auto-calculate from HLS latency
        # At minimum, need to hold one entry per in-flight packet
        # Rule: FIFO depth = 2 * HLS_latency + margin_of_4
        params.metadata_fifo_depth = max(4, 2 * hls_latency + 4)

        # Round up to power of 2 for efficient implementation
        params.metadata_fifo_depth = 2 ** math.ceil(math.log2(params.metadata_fifo_depth))

        # Register slices: based on data width and frequency
        # Rule: insert register slices if data_width > 256 or clock > 250 MHz
        if data_width > 256:
            params.num_reg_slices = 2
        elif data_width > 128:
            params.num_reg_slices = 1
        else:
            params.num_reg_slices = 0

        # Clock crossing detection
        if abs(shell_clock_mhz - hls_clock_mhz) > 1.0:
            params.clock_crossing = True
            params.num_reg_slices = max(params.num_reg_slices, 1)

        # TUSER strategy
        if metadata_must_span:
            params.tuser_update_strategy = "pass_through"
        else:
            params.tuser_update_strategy = "length_modifying"

        return params

    def select_ml(
        self, hls_latency: int, shell_clock_mhz: float, hls_clock_mhz: float,
        data_width: int, metadata_must_span: bool = True
    ) -> AdapterParams:
        try:
            from ml.optimize import ml_optimize_params
            cfg = ml_optimize_params(
                hls_latency=hls_latency,
                shell_clock_mhz=shell_clock_mhz,
                hls_clock_mhz=hls_clock_mhz,
                data_width=data_width,
                metadata_must_span=metadata_must_span,
            )
            if cfg is not None:
                params = AdapterParams()
                params.metadata_fifo_depth = cfg.get("metadata_fifo_depth", 8)
                params.num_reg_slices = cfg.get("num_reg_slices", 0)
                params.clock_crossing = cfg.get("clock_crossing", False)
                params.tuser_update_strategy = cfg.get("tuser_update_strategy", "pass_through")
                params.pass_tuser_to_hls = cfg.get("pass_tuser_to_hls", False)
                params.shell_clock_freq_mhz = cfg.get("shell_clock_freq_mhz", shell_clock_mhz)
                params.hls_clock_freq_mhz = cfg.get("hls_clock_freq_mhz", hls_clock_mhz)
                return params
        except (ImportError, Exception) as e:
            import logging
            logging.getLogger(__name__).info(
                "ML optimizer unavailable (%s), using heuristic fallback", e
            )
        return self.select(hls_latency, shell_clock_mhz, hls_clock_mhz, data_width, metadata_must_span)


def select_params(
    hls_latency: int,
    shell_clock_mhz: float = 250.0,
    hls_clock_mhz: float = 250.0,
    data_width: int = 512,
    metadata_must_span: bool = True,
) -> AdapterParams:
    selector = AdapterParameterSelector()
    return selector.select(
        hls_latency=hls_latency,
        shell_clock_mhz=shell_clock_mhz,
        hls_clock_mhz=hls_clock_mhz,
        data_width=data_width,
        metadata_must_span=metadata_must_span,
    )

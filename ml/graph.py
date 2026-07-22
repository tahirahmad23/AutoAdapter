from dataclasses import dataclass, field
from typing import Optional


@dataclass
class AdapterGraphNode:
    stage: str
    data_width: int
    tuser_width: int
    fifo_depth: int
    reg_slices: int
    clock_freq_mhz: float
    shell: int = 0


@dataclass
class AdapterGraphEdge:
    source: str
    target: str
    data_width: int


@dataclass
class AdapterGraph:
    nodes: list[AdapterGraphNode] = field(default_factory=list)
    edges: list[AdapterGraphEdge] = field(default_factory=list)

    def to_feature_vector(self) -> list[float]:
        features = []
        for node in self.nodes:
            features.extend([
                float(node.data_width) / 512.0,
                float(node.tuser_width) / 64.0,
                float(node.fifo_depth) / 32.0,
                float(node.reg_slices) / 2.0,
                node.clock_freq_mhz / 500.0,
                float(node.shell),
            ])
        return features

    def to_pyg_data(self):
        try:
            import torch
            from torch_geometric.data import Data
        except ImportError:
            raise ImportError("PyTorch Geometric required for GNN inference")

        features = self.to_feature_vector()
        num_nodes = len(self.nodes)
        num_features = len(features) // num_nodes if num_nodes > 0 else 0
        x = torch.tensor(features, dtype=torch.float).reshape(num_nodes, num_features)

        edge_index = []
        for i, edge in enumerate(self.edges):
            src_idx = next(j for j, n in enumerate(self.nodes) if n.stage == edge.source)
            dst_idx = next(j for j, n in enumerate(self.nodes) if n.stage == edge.target)
            edge_index.append([src_idx, dst_idx])

        if not edge_index:
            edge_index = [[0, 0]]

        edge_index = torch.tensor(edge_index, dtype=torch.long).t().contiguous()

        return Data(x=x, edge_index=edge_index)

    def summary(self) -> str:
        lines = ["Adapter Graph:"]
        for node in self.nodes:
            lines.append(
                f"  {node.stage:15s}  data={node.data_width:4d}  "
                f"tuser={node.tuser_width:2d}  fifo={node.fifo_depth:2d}  "
                f"slices={node.reg_slices}  clock={node.clock_freq_mhz} MHz"
            )
        for edge in self.edges:
            lines.append(f"  {edge.source} -> {edge.target}  ({edge.data_width}-bit)")
        return "\n".join(lines)


def build_adapter_graph(
    hls_latency: int,
    shell_clock_mhz: float = 250.0,
    hls_clock_mhz: float = 250.0,
    data_width: int = 512,
    tuser_width: int = 64,
    metadata_must_span: bool = True,
) -> AdapterGraph:
    import math

    depth = max(4, 2 * hls_latency + 4)
    depth = 2 ** math.ceil(math.log2(depth))

    if data_width > 256:
        reg_slices = 2
    elif data_width > 128:
        reg_slices = 1
    else:
        reg_slices = 0

    clock_crossing = abs(shell_clock_mhz - hls_clock_mhz) > 1.0
    if clock_crossing:
        reg_slices = max(reg_slices, 1)

    if clock_crossing:
        stage_names = ["ingress", "cdc_fifo_in", "hls_wrapper", "cdc_fifo_out", "egress"]
    else:
        stage_names = ["ingress", "meta_fifo", "hls_wrapper", "egress"]
        reg_slices_final = reg_slices
        if reg_slices > 0:
            stage_names.append("reg_slice")

    graph = AdapterGraph()
    for i, name in enumerate(stage_names):
        fd = depth if name in ("meta_fifo", "cdc_fifo_in", "cdc_fifo_out") else 0
        rs = reg_slices if "reg_slice" in name else 0
        cf = shell_clock_mhz if name in ("ingress", "meta_fifo", "cdc_fifo_in", "egress", "reg_slice") else hls_clock_mhz
        graph.nodes.append(AdapterGraphNode(
            stage=name,
            data_width=data_width,
            tuser_width=tuser_width,
            fifo_depth=fd,
            reg_slices=rs,
            clock_freq_mhz=cf,
        ))

    for i in range(len(stage_names) - 1):
        graph.edges.append(AdapterGraphEdge(
            source=stage_names[i],
            target=stage_names[i + 1],
            data_width=data_width,
        ))

    return graph

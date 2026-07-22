import argparse
import math
import os
import sys
from pathlib import Path

import pandas as pd
import numpy as np

try:
    import torch
    import torch.nn.functional as F
    from torch_geometric.data import Data
    from torch_geometric.loader import DataLoader
except ImportError:
    print("PyTorch Geometric required. Install with: pip install torch_geometric")
    sys.exit(1)

try:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    HAS_MPL = True
except ImportError:
    HAS_MPL = False

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from ml.graph import AdapterGraph, AdapterGraphNode, AdapterGraphEdge
from ml.model import AdapterGNN


def parse_accel(accel: str) -> int:
    return int(accel.split("_")[-1].replace("lat", ""))


def build_graph_from_config(accel: str, fifo_depth: int, reg_slices: int, clock_crossing: int, shell: int = 0) -> AdapterGraph:
    hls_latency = parse_accel(accel)
    data_width = 512
    tuser_width = 64
    shell_clock_mhz = 250.0
    hls_clock_mhz = 322.0 if clock_crossing else 250.0

    if clock_crossing:
        stage_names = ["ingress", "cdc_fifo_in", "hls_wrapper", "cdc_fifo_out", "egress"]
    else:
        stage_names = ["ingress", "meta_fifo", "hls_wrapper", "egress"]
        if reg_slices > 0:
            stage_names.append("reg_slice")

    graph = AdapterGraph()
    for name in stage_names:
        fd = fifo_depth if "fifo" in name else 0
        rs = reg_slices if "slice" in name else 0
        cf = shell_clock_mhz if name in ("ingress", "meta_fifo", "cdc_fifo_in", "egress", "reg_slice") else hls_clock_mhz
        graph.nodes.append(AdapterGraphNode(
            stage=name,
            data_width=data_width,
            tuser_width=tuser_width,
            fifo_depth=fd,
            reg_slices=rs,
            clock_freq_mhz=cf,
            shell=shell,
        ))

    for i in range(len(stage_names) - 1):
        graph.edges.append(AdapterGraphEdge(
            source=stage_names[i],
            target=stage_names[i + 1],
            data_width=data_width,
        ))

    return graph


def load_data(csv_path: str):
    df = pd.read_csv(csv_path)
    data_list = []

    for _, row in df.iterrows():
        graph = build_graph_from_config(
            accel=row["accel"],
            fifo_depth=int(row["fifo_depth"]),
            reg_slices=int(row["reg_slices"]),
            clock_crossing=int(row["clock_crossing"]),
            shell=int(row.get("shell", 0)),
        )
        pyg_data = graph.to_pyg_data()

        luts = float(row["luts"])
        ffs = float(row["ffs"])
        wns_str = row["wns"]
        wns = float(wns_str) if wns_str not in ("N/A", "") else 0.0
        tns_str = row["tns"]
        tns = float(tns_str) if tns_str not in ("N/A", "") else 0.0

        pyg_data.y = torch.tensor(
            [luts / 2000.0, ffs / 3000.0, max(0, wns) / 1.0, max(0, tns) / 10.0],
            dtype=torch.float,
        ).unsqueeze(0)
        data_list.append(pyg_data)

    return data_list, df


def train(data_list, epochs=200, batch_size=16, lr=0.01, out_path="ml/adapter_gnn_model.pth"):
    n = len(data_list)
    indices = np.random.RandomState(42).permutation(n)
    split = int(n * 0.8)
    train_idx = indices[:split]
    test_idx = indices[split:]

    train_data = [data_list[i] for i in train_idx]
    test_data = [data_list[i] for i in test_idx]

    print(f"Training samples: {len(train_data)}, Test samples: {len(test_data)}")

    model = AdapterGNN()
    model.train()
    optimizer = torch.optim.Adam(model.parameters(), lr=lr)
    loader = DataLoader(train_data, batch_size=batch_size, shuffle=True)

    for epoch in range(epochs):
        total_loss = 0
        for batch in loader:
            optimizer.zero_grad()
            out = model(batch.x, batch.edge_index, batch.batch)
            loss = F.mse_loss(out, batch.y)
            loss.backward()
            optimizer.step()
            total_loss += loss.item()
        if (epoch + 1) % 50 == 0:
            avg_loss = total_loss / len(loader)
            print(f"  Epoch {epoch+1:3d}/{epochs}  Loss: {avg_loss:.6f}")

    torch.save(model.state_dict(), out_path)
    print(f"Model saved to {out_path}")

    test_loss = evaluate(model, test_data)
    print(f"Test MSE: {test_loss:.6f}")
    return model, test_data


def evaluate(model, test_data):
    model.eval()
    loader = DataLoader(test_data, batch_size=16)
    total_loss = 0
    with torch.no_grad():
        for batch in loader:
            out = model(batch.x, batch.edge_index, batch.batch)
            loss = F.mse_loss(out, batch.y)
            total_loss += loss.item()
    return total_loss / len(loader) if loader else 0


def plot_predictions(model, data_list, df, out_dir="ml/evaluation_plots"):
    if not HAS_MPL:
        print("matplotlib not installed, skipping plots")
        return

    model.eval()
    os.makedirs(out_dir, exist_ok=True)

    targets_names = ["LUT", "FF", "WNS", "TNS"]
    targets_scale = [2000.0, 3000.0, 1.0, 10.0]
    targets_unit = ["", "", "ns", "ns"]

    all_preds = []
    all_targets = []

    with torch.no_grad():
        for d in data_list:
            pred = model(d.x, d.edge_index, torch.zeros(d.x.size(0), dtype=torch.long))
            all_preds.append(pred.squeeze().numpy())
            all_targets.append(d.y.squeeze().numpy())

    all_preds = np.array(all_preds)
    all_targets = np.array(all_targets)

    for i, name in enumerate(targets_names):
        preds = all_preds[:, i] * targets_scale[i]
        targets = all_targets[:, i] * targets_scale[i]

        fig, ax = plt.subplots(figsize=(6, 6))
        ax.scatter(targets, preds, alpha=0.6, s=20)
        lims = [
            min(min(targets), min(preds)),
            max(max(targets), max(preds)),
        ]
        ax.plot(lims, lims, "r--", lw=1, label="Perfect")
        ax.set_xlabel(f"Actual {name} ({targets_unit[i]})")
        ax.set_ylabel(f"Predicted {name} ({targets_unit[i]})")
        ax.set_title(f"{name}: Predicted vs Actual")
        ax.legend()
        ax.grid(True, alpha=0.3)
        fig.tight_layout()
        path = os.path.join(out_dir, f"{name.lower()}_scatter.png")
        fig.savefig(path, dpi=150)
        plt.close(fig)
        print(f"  Saved {path}")

        mae = np.mean(np.abs(preds - targets))
        mape = np.mean(np.abs((preds - targets) / (targets + 1e-10))) * 100
        print(f"  {name}: MAE={mae:.2f}{targets_unit[i]}, MAPE={mape:.1f}%")

    all_preds_flat = all_preds * np.array(targets_scale)
    all_targets_flat = all_targets * np.array(targets_scale)
    overall_mae = np.mean(np.abs(all_preds_flat - all_targets_flat))
    print(f"\nOverall MAE (all targets): {overall_mae:.2f}")


def main():
    parser = argparse.ArgumentParser(description="Train AutoAdapter GNN")
    parser.add_argument("--csv", default="data/sweep_results_combined.csv",
                        help="Path to sweep results CSV")
    parser.add_argument("--epochs", type=int, default=200,
                        help="Number of training epochs")
    parser.add_argument("--batch-size", type=int, default=16,
                        help="Batch size")
    parser.add_argument("--lr", type=float, default=0.01,
                        help="Learning rate")
    parser.add_argument("--out-model", default="ml/adapter_gnn_model.pth",
                        help="Output model path")
    parser.add_argument("--out-plots", default="ml/evaluation_plots",
                        help="Output plots directory")
    args = parser.parse_args()

    print("Loading data...")
    data_list, df = load_data(args.csv)
    print(f"Loaded {len(data_list)} configurations")

    model, test_data = train(
        data_list,
        epochs=args.epochs,
        batch_size=args.batch_size,
        lr=args.lr,
        out_path=args.out_model,
    )

    plot_predictions(model, data_list, df, out_dir=args.out_plots)


if __name__ == "__main__":
    main()

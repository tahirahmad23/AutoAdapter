# ML-Based Parameter Optimization (Future Work)

This module implements a Graph Neural Network (GNN) approach for predicting adapter resource usage and timing closure, serving as an alternative to the analytical heuristics in `generator/adapter_params.py`.

## Status

This is **future work** and is not part of the core AutoAdapter contribution. It was used in the paper only for an ablation study comparing ML-based vs. heuristic parameter selection.

## Contents

- `model.py` - GNN architecture (2-layer GCN) for predicting LUTs, FFs, WNS, TNS
- `graph.py` - Adapter dataflow graph construction for PyTorch Geometric
- `optimize.py` - ML-based parameter optimization driver
- `train_gnn.py` - Training script
- `adapter_gnn_model.pth` - Pre-trained model weights
- `evaluation_plots/` - Prediction accuracy scatter plots

## Usage

```bash
# Train the GNN model
python ml/train_gnn.py --data data/sweep_results_final.csv

# Optimize adapter parameters using ML
python ml/optimize.py --isl isl/opennic_250mhz.json --accel flow_hash
```

## Note

The analytical heuristics (`generator/adapter_params.py`) are recommended for production use. The ML approach requires PyTorch Geometric and additional training data.

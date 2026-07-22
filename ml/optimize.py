import math
import logging

logger = logging.getLogger(__name__)


def _heuristic_config(
    hls_latency: int,
    shell_clock_mhz: float = 250.0,
    hls_clock_mhz: float = 250.0,
    data_width: int = 512,
    metadata_must_span: bool = True,
) -> dict:
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

    return {
        "metadata_fifo_depth": depth,
        "num_reg_slices": reg_slices,
        "clock_crossing": clock_crossing,
        "tuser_update_strategy": "pass_through" if metadata_must_span else "length_modifying",
        "pass_tuser_to_hls": False,
        "shell_clock_freq_mhz": shell_clock_mhz,
        "hls_clock_freq_mhz": hls_clock_mhz,
    }


def ml_optimize_params(
    hls_latency: int,
    shell_clock_mhz: float = 250.0,
    hls_clock_mhz: float = 250.0,
    data_width: int = 512,
    tuser_width: int = 64,
    metadata_must_span: bool = True,
) -> dict:
    try:
        from ml.model import load_model, predict, HAS_TORCH
        from ml.graph import build_adapter_graph

        if not HAS_TORCH:
            logger.info("ML not available (PyTorch not installed), using heuristic fallback")
            return _heuristic_config(
                hls_latency, shell_clock_mhz, hls_clock_mhz, data_width, metadata_must_span
            )

        model, status = load_model()
        if status != "loaded":
            logger.info("ML model %s, using heuristic fallback", status)
            return _heuristic_config(
                hls_latency, shell_clock_mhz, hls_clock_mhz, data_width, metadata_must_span
            )

        candidate_configs = _generate_candidates(hls_latency, data_width)
        best_config = _search_with_model(
            model, candidate_configs,
            hls_latency, shell_clock_mhz, hls_clock_mhz,
            data_width, tuser_width, metadata_must_span
        )

        if best_config:
            logger.info("ML optimizer selected: FIFO depth=%d, slices=%d",
                        best_config["metadata_fifo_depth"], best_config["num_reg_slices"])
            return best_config

    except ImportError as e:
        logger.debug("ML optimizer not importable (%s), using heuristic", e)

    return _heuristic_config(
        hls_latency, shell_clock_mhz, hls_clock_mhz, data_width, metadata_must_span
    )


def _generate_candidates(hls_latency: int, data_width: int) -> list[dict]:
    depths = [4, 8, 16, 32, 64]
    slices_opts = [0, 1, 2]
    if data_width > 256:
        slices_opts = [1, 2, 3]

    candidates = []
    for d in depths:
        for s in slices_opts:
            if d >= max(4, hls_latency):
                candidates.append({"depth": d, "slices": s})
    return candidates


def _search_with_model(model, candidates, hls_latency, shell_clock_mhz, hls_clock_mhz, data_width, tuser_width, metadata_must_span):
    import torch
    from ml.graph import build_adapter_graph

    best_score = float("inf")
    best_config = None

    for cand in candidates:
        graph = build_adapter_graph(
            hls_latency=hls_latency,
            shell_clock_mhz=shell_clock_mhz,
            hls_clock_mhz=hls_clock_mhz,
            data_width=data_width,
            tuser_width=tuser_width,
            metadata_must_span=metadata_must_span,
        )

        data = graph.to_pyg_data()
        pred = predict(model, data).squeeze()

        lut_pred = pred[0].item() if pred.dim() > 0 else 0.5
        ff_pred = pred[1].item() if pred.dim() > 1 else 0.5
        slack_pred = pred[2].item() if pred.dim() > 2 else 0.0
        latency_pred = pred[3].item() if pred.dim() > 3 else 0.0

        score = (lut_pred + ff_pred) * 100.0 - slack_pred * 10.0 + latency_pred * 5.0

        if score < best_score:
            best_score = score
            clock_crossing = abs(shell_clock_mhz - hls_clock_mhz) > 1.0
            best_config = {
                "metadata_fifo_depth": cand["depth"],
                "num_reg_slices": cand["slices"],
                "clock_crossing": clock_crossing,
                "tuser_update_strategy": "pass_through" if metadata_must_span else "length_modifying",
                "pass_tuser_to_hls": False,
                "shell_clock_freq_mhz": shell_clock_mhz,
                "hls_clock_freq_mhz": hls_clock_mhz,
            }

    return best_config


def predict(model, data):
    import torch
    model.eval()
    with torch.no_grad():
        out = model(data.x, data.edge_index, torch.zeros(data.x.size(0), dtype=torch.long))
    return out


def optimize_greedy(
    hls_latency: int,
    shell_clock_mhz: float = 250.0,
    hls_clock_mhz: float = 250.0,
    data_width: int = 512,
    metadata_must_span: bool = True,
) -> dict:
    return _heuristic_config(
        hls_latency, shell_clock_mhz, hls_clock_mhz, data_width, metadata_must_span
    )

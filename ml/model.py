try:
    import torch
    import torch.nn as nn
    import torch.nn.functional as F
    from torch_geometric.nn import GCNConv, global_mean_pool
    from torch_geometric.data import Data
    from torch_geometric.loader import DataLoader

    class AdapterGNN(torch.nn.Module):
        def __init__(self, in_channels=6, hidden_channels=64, out_channels=4):
            super().__init__()
            self.conv1 = GCNConv(in_channels, hidden_channels)
            self.conv2 = GCNConv(hidden_channels, hidden_channels)
            self.fc = nn.Linear(hidden_channels, out_channels)

        def forward(self, x, edge_index, batch):
            x = self.conv1(x, edge_index)
            x = F.relu(x)
            x = self.conv2(x, edge_index)
            x = F.relu(x)
            x = global_mean_pool(x, batch)
            x = self.fc(x)
            return x

    ML_AVAILABLE = True
    HAS_TORCH = True
except ImportError:
    ML_AVAILABLE = False
    HAS_TORCH = False


MODEL_PATH = "ml/adapter_gnn_model.pth"


def create_model() -> object:
    if not ML_AVAILABLE:
        return None
    return AdapterGNN()


def load_model(path: str = None):
    if not ML_AVAILABLE:
        return None, "unavailable (PyTorch Geometric not installed)"

    global MODEL_PATH
    model = AdapterGNN()
    model_path = path or MODEL_PATH or "ml/adapter_gnn_model.pth"

    try:
        state = torch.load(model_path, map_location="cpu")
        model.load_state_dict(state)
        model.eval()
        MODEL_PATH = model_path
        return model, "loaded"
    except (FileNotFoundError, RuntimeError) as e:
        return model, f"unavailable ({e})"


def train_model(data_list, out_path: str = "ml/adapter_gnn_model.pth", epochs: int = 200):
    if not ML_AVAILABLE:
        print("PyTorch Geometric required for training")
        return None

    model = AdapterGNN()
    model.train()
    optimizer = torch.optim.Adam(model.parameters(), lr=0.01)
    loader = DataLoader(data_list, batch_size=16, shuffle=True)
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
            print(f"Epoch {epoch+1}/{epochs}, Loss: {total_loss/len(loader):.4f}")

    torch.save(model.state_dict(), out_path)
    global MODEL_PATH
    MODEL_PATH = out_path
    print(f"Model saved to {out_path}")
    return model


def predict(model, data: Data):
    import torch
    model.eval()
    with torch.no_grad():
        out = model(data.x, data.edge_index, torch.zeros(data.x.size(0), dtype=torch.long))
    return out

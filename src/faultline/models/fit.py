"""점검 우선순위 모형. 같은 특징으로 HGB(트리)와 PyTorch(신경망)를 비교한다."""

from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import HistGradientBoostingClassifier

from faultline.models.features import FEATURES, NUMERIC


def fit_hgb(X: pd.DataFrame, y: np.ndarray, seed: int = 0) -> HistGradientBoostingClassifier:
    cat_mask = [c == "category" for c in FEATURES]
    m = HistGradientBoostingClassifier(
        max_iter=140,
        learning_rate=0.09,
        max_leaf_nodes=24,
        min_samples_leaf=40,
        l2_regularization=1.0,
        categorical_features=cat_mask,
        random_state=seed,
    )
    return m.fit(X[FEATURES], y.astype(int))


def predict_hgb(m: HistGradientBoostingClassifier, X: pd.DataFrame) -> np.ndarray:
    return m.predict_proba(X[FEATURES])[:, 1]


class MlpModel:
    """설비 종류 임베딩 + 수치 특징 → 4주 안 고장 확률. 같은 입력, 같은 라벨로 트리 모형과 겨룬다."""

    def __init__(self, seed: int = 0, epochs: int = 8):
        self.seed, self.epochs = seed, epochs
        self.mu = self.sd = None
        self.net = None

    def _num(self, X: pd.DataFrame) -> np.ndarray:
        v = X[NUMERIC].to_numpy(dtype=np.float32)
        return (v - self.mu) / self.sd

    def fit(self, X: pd.DataFrame, y: np.ndarray) -> MlpModel:
        import torch
        from torch import nn

        torch.manual_seed(self.seed)
        torch.set_num_threads(2)
        v = X[NUMERIC].to_numpy(dtype=np.float32)
        self.mu, self.sd = v.mean(0), v.std(0) + 1e-6
        xn = torch.tensor(self._num(X))
        xc = torch.tensor(X["category"].to_numpy(), dtype=torch.long)
        yt = torch.tensor(y.astype(np.float32))

        class Net(nn.Module):
            def __init__(self, n_in: int):
                super().__init__()
                self.emb = nn.Embedding(8, 4)
                self.body = nn.Sequential(
                    nn.Linear(n_in + 4, 64),
                    nn.ReLU(),
                    nn.Dropout(0.1),
                    nn.Linear(64, 32),
                    nn.ReLU(),
                    nn.Linear(32, 1),
                )

            def forward(self, num, cat):
                return self.body(torch.cat([num, self.emb(cat)], dim=1)).squeeze(1)

        self.net = Net(xn.shape[1])
        opt = torch.optim.Adam(self.net.parameters(), lr=2e-3, weight_decay=1e-5)
        pos = float(yt.mean().clamp(min=1e-3))
        loss_fn = nn.BCEWithLogitsLoss(pos_weight=torch.tensor(min(1.0 / pos - 1.0, 8.0)))
        n = len(yt)
        g = torch.Generator().manual_seed(self.seed)
        self.net.train()
        for _ in range(self.epochs):
            perm = torch.randperm(n, generator=g)
            for i in range(0, n, 1024):
                b = perm[i : i + 1024]
                opt.zero_grad()
                loss_fn(self.net(xn[b], xc[b]), yt[b]).backward()
                opt.step()
        self.net.eval()
        return self

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        import torch

        with torch.no_grad():
            z = self.net(torch.tensor(self._num(X)), torch.tensor(X["category"].to_numpy(), dtype=torch.long))
        return torch.sigmoid(z).numpy()

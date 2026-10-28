"""A compact random forest: regression trees, feature subsampling, bagging."""

from __future__ import annotations

import random
from dataclasses import dataclass, field

import numpy as np

MAX_THRESHOLDS = 12


@dataclass
class Node:
    feature: int = -1
    threshold: float = 0.0
    value: float = 0.0
    left: Node | None = None
    right: Node | None = None


@dataclass
class Forest:
    trees: list[Node] = field(default_factory=list)
    feature_importance: list[float] = field(default_factory=list)
    seed: int = 0

    def predict(self, features: np.ndarray) -> np.ndarray:
        outputs = np.column_stack([predict_tree(tree, features) for tree in self.trees])
        return outputs.mean(axis=1)


def _best_split(
    x: np.ndarray,
    y: np.ndarray,
    feature_ids: list[int],
    min_leaf: int,
    importance: np.ndarray,
) -> tuple[int, float] | None:
    total = float(y.var()) * len(y)
    if total <= 1e-12:
        return None
    best_gain = 0.0
    best: tuple[int, float] | None = None
    for feature in feature_ids:
        column = x[:, feature]
        candidates = np.unique(column)
        if candidates.size < 2:
            continue
        if candidates.size > MAX_THRESHOLDS:
            candidates = np.quantile(column, np.linspace(0.0, 1.0, MAX_THRESHOLDS + 2)[1:-1])
        else:
            candidates = (candidates[:-1] + candidates[1:]) / 2.0
        for threshold in candidates:
            left_mask = column <= threshold
            left_count = int(left_mask.sum())
            right_count = len(y) - left_count
            if left_count < min_leaf or right_count < min_leaf:
                continue
            score = float(y[left_mask].var()) * left_count + float(y[~left_mask].var()) * right_count
            gain = total - score
            if gain > best_gain + 1e-12:
                best_gain = gain
                best = (feature, float(threshold))
    if best is not None:
        importance[best[0]] += best_gain / max(total, 1e-12)
    return best


def build_tree(x: np.ndarray, y: np.ndarray, depth: int, max_depth: int, min_leaf: int, importance: np.ndarray, feature_ids: list[int]) -> Node:
    node = Node(value=float(y.mean()))
    if depth >= max_depth or len(y) < min_leaf * 2 or y.var() <= 1e-12:
        return node
    split = _best_split(x, y, feature_ids, min_leaf, importance)
    if split is None:
        return node
    feature, threshold = split
    mask = x[:, feature] <= threshold
    node.feature = feature
    node.threshold = threshold
    node.left = build_tree(x[mask], y[mask], depth + 1, max_depth, min_leaf, importance, feature_ids)
    node.right = build_tree(x[~mask], y[~mask], depth + 1, max_depth, min_leaf, importance, feature_ids)
    return node


def predict_tree(tree: Node, features: np.ndarray) -> np.ndarray:
    outputs = np.empty(len(features))
    stack: list[tuple[Node, np.ndarray]] = [(tree, np.arange(len(features)))]
    while stack:
        node, rows = stack.pop()
        if node.left is None or node.right is None:
            outputs[rows] = node.value
            continue
        column = features[rows, node.feature]
        stack.append((node.left, rows[column <= node.threshold]))
        stack.append((node.right, rows[column > node.threshold]))
    return outputs


def fit_forest(x: np.ndarray, y: np.ndarray, seed: int, n_trees: int = 60, max_depth: int = 5, min_leaf: int = 3) -> Forest:
    """Bagged regression trees. On binary labels the variance split matches gini."""
    n_features = x.shape[1]
    subset_size = max(2, round(n_features ** 0.5))
    importance = np.zeros(n_features)
    trees: list[Node] = []
    for tree_index in range(n_trees):
        rng = random.Random(seed * 1000 + tree_index)
        rows = np.array([rng.randrange(len(y)) for _ in range(len(y))], dtype=int)
        sampled = sorted(rng.sample(range(n_features), subset_size))
        trees.append(build_tree(x[rows], y[rows], 0, max_depth, min_leaf, importance, sampled))
    feature_importance = importance / max(float(importance.sum()), 1e-12)
    return Forest(trees=trees, feature_importance=feature_importance.tolist(), seed=seed)

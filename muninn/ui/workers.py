"""Muninn UI — QThread Workers.

R3: Worker = QObject + moveToThread, NOT QThread subclass.
R12: Cancel old worker BEFORE launching new one.
moveToThread BEFORE connect (bug #10).
"""

import numpy as np
from PyQt6.QtCore import QObject, pyqtSignal


class LaplacianWorker(QObject):
    """Compute spectral layout from adjacency data in a background thread.

    B-UI-03: Top N concepts by degree (N=1000), scipy.sparse, eigsh().
    Guard < 3 nodes: linear fallback.
    Fallback: eigsh fails -> spring layout.
    """

    finished = pyqtSignal(object)  # list of (x, y) positions
    progress = pyqtSignal(int)     # 0-100
    error = pyqtSignal(str)

    def __init__(self, nodes, edges, top_n=1000):
        super().__init__()  # NO parent (R3)
        self._stop = False
        self._nodes = nodes
        self._edges = edges
        self._top_n = top_n

    def run(self):
        try:
            n = len(self._nodes)

            if n == 0:
                self.finished.emit([])
                return

            if n == 1:
                self.finished.emit([(0.5, 0.5)])
                return

            if n == 2:
                self.finished.emit([(0.3, 0.5), (0.7, 0.5)])
                return

            self.progress.emit(10)

            # Filter to top N by degree if too many nodes
            if n > self._top_n:
                degrees = [0] * n
                for ia, ib, w in self._edges:
                    if ia < n:
                        degrees[ia] += 1
                    if ib < n:
                        degrees[ib] += 1
                top_indices = sorted(range(n), key=lambda i: degrees[i], reverse=True)[:self._top_n]
                idx_map = {old: new for new, old in enumerate(top_indices)}
                filtered_edges = []
                for ia, ib, w in self._edges:
                    if ia in idx_map and ib in idx_map:
                        filtered_edges.append((idx_map[ia], idx_map[ib], w))
                n = len(top_indices)
                edges = filtered_edges
            else:
                top_indices = list(range(n))
                edges = self._edges

            if self._stop:
                return

            self.progress.emit(30)

            # Build sparse adjacency matrix
            from scipy.sparse import csr_matrix
            from scipy.sparse.linalg import eigsh

            rows, cols, vals = [], [], []
            for ia, ib, w in edges:
                if ia < n and ib < n:
                    rows.extend([ia, ib])
                    cols.extend([ib, ia])
                    vals.extend([w, w])

            if not rows:
                # No edges: grid layout
                positions = self._grid_layout(n)
                self.finished.emit(positions)
                return

            adj = csr_matrix((vals, (rows, cols)), shape=(n, n))

            if self._stop:
                return

            self.progress.emit(50)

            # Laplacian = D - A
            degrees_diag = np.array(adj.sum(axis=1)).flatten()
            # Avoid division by zero
            degrees_diag[degrees_diag == 0] = 1
            from scipy.sparse import diags as sparse_diags, eye as sparse_eye
            D_inv_sqrt = sparse_diags(1.0 / np.sqrt(degrees_diag))
            # Normalized Laplacian: I - D^(-1/2) A D^(-1/2)
            L_norm = sparse_eye(n) - D_inv_sqrt @ adj @ D_inv_sqrt

            if self._stop:
                return

            self.progress.emit(70)

            # Spectral embedding: 2nd and 3rd smallest eigenvectors
            try:
                k = min(3, n - 1)
                eigenvalues, eigenvectors = eigsh(L_norm, k=k, which='SM', maxiter=500)
                # Use 2nd and 3rd eigenvectors for x, y
                if k >= 3:
                    x = eigenvectors[:, 1]
                    y = eigenvectors[:, 2]
                elif k == 2:
                    x = eigenvectors[:, 1]
                    y = np.zeros(n)
                else:
                    x = eigenvectors[:, 0]
                    y = np.zeros(n)
            except Exception:
                # Fallback: spring layout
                x, y = self._spring_layout(n, edges)

            if self._stop:
                return

            self.progress.emit(90)

            # Normalize to [0.1, 0.9]
            def normalize(arr):
                mn, mx = arr.min(), arr.max()
                if mx - mn < 1e-10:
                    return np.full_like(arr, 0.5)
                return 0.1 + 0.8 * (arr - mn) / (mx - mn)

            x = normalize(x)
            y = normalize(y)

            # Build full position list (non-top-N get random positions)
            full_positions = [(0.5, 0.5)] * len(self._nodes)
            for new_idx, old_idx in enumerate(top_indices):
                full_positions[old_idx] = (float(x[new_idx]), float(y[new_idx]))

            # Fill remaining with jittered positions near center
            import random
            rng = random.Random(42)
            for i in range(len(self._nodes)):
                if full_positions[i] == (0.5, 0.5) and i not in top_indices:
                    full_positions[i] = (
                        0.3 + rng.random() * 0.4,
                        0.3 + rng.random() * 0.4,
                    )

            self.progress.emit(100)
            self.finished.emit(full_positions)

        except Exception as e:
            self.error.emit(str(e))

    def _spring_layout(self, n, edges, iterations=50):
        """Simple spring layout fallback."""
        rng = np.random.RandomState(42)
        x = rng.rand(n)
        y = rng.rand(n)

        for _ in range(iterations):
            if self._stop:
                return x, y
            # Repulsion
            for i in range(n):
                for j in range(i + 1, min(i + 50, n)):
                    dx = x[i] - x[j]
                    dy = y[i] - y[j]
                    dist = max(np.hypot(dx, dy), 0.01)
                    force = 0.01 / (dist * dist)
                    x[i] += dx * force
                    y[i] += dy * force
                    x[j] -= dx * force
                    y[j] -= dy * force

            # Attraction (edges)
            for ia, ib, w in edges:
                if ia < n and ib < n:
                    dx = x[ib] - x[ia]
                    dy = y[ib] - y[ia]
                    dist = max(np.hypot(dx, dy), 0.01)
                    force = dist * 0.05
                    x[ia] += dx * force
                    y[ia] += dy * force
                    x[ib] -= dx * force
                    y[ib] -= dy * force

        return x, y

    def _grid_layout(self, n):
        """Grid layout for disconnected nodes."""
        import math
        cols = max(1, int(math.ceil(math.sqrt(n))))
        positions = []
        for i in range(n):
            row, col = divmod(i, cols)
            x = 0.1 + 0.8 * (col / max(cols - 1, 1))
            y = 0.1 + 0.8 * (row / max((n // cols), 1))
            positions.append((x, y))
        return positions

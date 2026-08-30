from __future__ import annotations

from collections.abc import Sequence
from hashlib import sha256

import numpy as np
import numpy.typing as npt


class DeterministicFixtureEmbeddingAdapter:
    dimension = 16
    model_id = "fixture-deterministic-embedding"
    model_revision = "task14-fixture@1"

    def embed_passages(self, texts: Sequence[str]) -> npt.NDArray[np.float32]:
        return self._embed(texts)

    def embed_query(self, text: str) -> npt.NDArray[np.float32]:
        return self._embed([text])

    def _embed(self, texts: Sequence[str]) -> npt.NDArray[np.float32]:
        vectors = np.zeros((len(texts), self.dimension), dtype=np.float32)
        for row, text in enumerate(texts):
            tokens = [token for token in _tokenize(text) if token not in {"passage", "query"}]
            if not tokens:
                tokens = [""]
            for token in tokens:
                digest = sha256(token.encode("utf-8")).digest()
                index = int.from_bytes(digest[:2], "big") % self.dimension
                vectors[row, index] += 1.0
        return vectors


def _tokenize(value: str) -> list[str]:
    normalized = "".join(char.lower() if char.isalnum() else " " for char in value)
    return normalized.split()

from __future__ import annotations

import os
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    import numpy as np
    from sentence_transformers import SentenceTransformer


DEFAULT_MODEL = "BAAI/bge-m3"
EMBEDDING_DIMENSIONS = 1024


class EmbeddingModelError(RuntimeError):
    pass


class BgeM3Embedder:
    """Lazy optional adapter; normal add/update flows never import ML packages."""

    def __init__(self, model_name: str = DEFAULT_MODEL):
        self.model_name = model_name

    @property
    def is_cached(self) -> bool:
        try:
            from huggingface_hub import try_to_load_from_cache

            required_files = (
                "config.json",
                "modules.json",
                "1_Pooling/config.json",
                "tokenizer_config.json",
            )
            if not all(
                isinstance(try_to_load_from_cache(self.model_name, name), str)
                for name in required_files
            ):
                return False
            weights = try_to_load_from_cache(self.model_name, "model.safetensors")
            if not isinstance(weights, str):
                weights = try_to_load_from_cache(self.model_name, "pytorch_model.bin")
            return isinstance(weights, str)
        except Exception:
            return False

    def load(self, *, allow_download: bool = False) -> "SentenceTransformer":
        if "model" not in self.__dict__:
            try:
                os.environ.setdefault("DISABLE_SAFETENSORS_CONVERSION", "true")
                from sentence_transformers import SentenceTransformer

                self.__dict__["model"] = SentenceTransformer(
                    self.model_name,
                    local_files_only=not allow_download,
                    model_kwargs={"use_safetensors": False},
                )
            except Exception as exc:
                raise EmbeddingModelError(
                    f"Could not load {self.model_name}: {exc}"
                ) from exc
        return self.__dict__["model"]

    def encode(
        self,
        texts: list[str],
        *,
        allow_download: bool = False,
        show_progress: bool = False,
    ) -> "np.ndarray":
        try:
            import numpy as np

            embeddings = self.load(allow_download=allow_download).encode(
                texts,
                batch_size=32,
                show_progress_bar=show_progress,
                convert_to_numpy=True,
                normalize_embeddings=True,
            )
            result = np.asarray(embeddings, dtype=np.float32)
            if result.ndim == 1:
                result = result.reshape(1, -1)
            if result.ndim != 2 or result.shape[1] != EMBEDDING_DIMENSIONS:
                received = result.shape[1] if result.ndim == 2 else result.shape
                raise ValueError(
                    f"Expected {EMBEDDING_DIMENSIONS} dimensions, received {received}."
                )
            return result
        except EmbeddingModelError:
            raise
        except Exception as exc:
            raise EmbeddingModelError(f"Could not create embeddings: {exc}") from exc


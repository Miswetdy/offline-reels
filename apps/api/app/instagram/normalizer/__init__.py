"""Browser-free production normalization queue."""

from app.instagram.normalizer.worker import InstagramNormalizerWorker

__all__ = ["InstagramNormalizerWorker"]

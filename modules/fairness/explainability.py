"""Optional model-specific explainability adapters for local model artifacts."""

from __future__ import annotations

from typing import Any


def shap_feature_values(
    model: Any, background: Any, samples: Any
) -> Any:
    """Compute SHAP KernelExplainer values for a supplied local model."""
    try:
        import shap
    except ImportError as error:
        raise RuntimeError("Install the optional 'shap' package to explain a model.") from error
    explainer = shap.KernelExplainer(model.predict, background)
    return explainer.shap_values(samples)

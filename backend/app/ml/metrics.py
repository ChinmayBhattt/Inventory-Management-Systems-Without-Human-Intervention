import numpy as np


def calculate_wape(actual: np.ndarray, predicted: np.ndarray) -> float:
    """
    Weighted Absolute Percentage Error (WAPE):
    WAPE = sum(|actual - predicted|) / sum(actual)
    Robust against zero-demand periods where MAPE produces division by zero.
    """
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    total_actual = np.sum(actual)
    if total_actual == 0:
        # If total demand is zero, check if predictions were also zero
        total_error = np.sum(np.abs(actual - predicted))
        return 0.0 if total_error == 0 else 1.0

    return float(np.sum(np.abs(actual - predicted)) / total_actual)


def calculate_mape(actual: np.ndarray, predicted: np.ndarray, epsilon: float = 1e-4) -> float:
    """
    Mean Absolute Percentage Error (MAPE):
    MAPE = (1 / N) * sum(|(actual - predicted) / max(actual, epsilon)|) * 100%
    Protected with small epsilon to prevent zero division.
    """
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)

    if len(actual) == 0:
        return 0.0

    # Avoid division by zero by substituting zeros with epsilon
    denominator = np.where(actual == 0, epsilon, actual)
    mape = np.mean(np.abs((actual - predicted) / denominator)) * 100.0
    return float(mape)


def calculate_rmse(actual: np.ndarray, predicted: np.ndarray) -> float:
    """Root Mean Squared Error (RMSE)."""
    actual = np.asarray(actual, dtype=float)
    predicted = np.asarray(predicted, dtype=float)
    if len(actual) == 0:
        return 0.0
    return float(np.sqrt(np.mean((actual - predicted) ** 2)))


---
language: python
tags: [documentation, docstrings, api-docs]
title: Docstring Conventions by Language
description: Python docstrings (Google/NumPy/Sphinx style), JSDoc for TypeScript, rustdoc for Rust, and godoc for Go
source: pattern
---

# Docstring Conventions by Language

## Python — Google Style (Recommended)
Clean, readable, widely adopted:

```python
def calculate_rmse(predictions: list[float], targets: list[float]) -> float:
    """Calculate root mean squared error between predictions and targets.

    Args:
        predictions: List of predicted values.
        targets: List of ground-truth values. Must be same length as predictions.

    Returns:
        The RMSE as a non-negative float.

    Raises:
        ValueError: If lists have different lengths or are empty.

    Example:
        >>> calculate_rmse([2.0, 3.0], [2.5, 2.5])
        0.5
    """
    if len(predictions) != len(targets):
        raise ValueError("predictions and targets must have the same length")
    return sqrt(mean((p - t) ** 2 for p, t in zip(predictions, targets)))
```

### NumPy Style (Alternative)

```python
def calculate_rmse(predictions, targets):
    """Calculate root mean squared error.

    Parameters
    ----------
    predictions : array-like
        Predicted values.
    targets : array-like
        Ground-truth values.

    Returns
    -------
    float
        The RMSE value.

    Raises
    ------
    ValueError
        If input lengths differ.
    """
```

### Sphinx / reStructuredText (Legacy)

```python
def calculate_rmse(predictions, targets):
    """Calculate root mean squared error.

    :param predictions: Predicted values.
    :param targets: Ground-truth values.
    :type predictions: list[float]
    :type targets: list[float]
    :returns: The RMSE.
    :rtype: float
    :raises ValueError: If input lengths differ.
    """
```

---

## TypeScript — JSDoc / TSDoc

```typescript
/**
 * Calculate root mean squared error between two numeric arrays.
 *
 * @param predictions - Predicted values. Must not be empty.
 * @param targets - Ground-truth values. Same length as predictions.
 * @returns The RMSE as a non-negative number.
 * @throws {Error} If arrays have mismatched lengths.
 *
 * @example
 * ```ts
 * calculateRmse([2.0, 3.0], [2.5, 2.5])
 * // => 0.5
 * ```
 */
function calculateRmse(predictions: number[], targets: number[]): number {
  if (predictions.length !== targets.length) {
    throw new Error("Array length mismatch");
  }
  const mean =
    predictions.reduce((sum, p, i) => sum + (p - targets[i]) ** 2, 0) /
    predictions.length;
  return Math.sqrt(mean);
}
```

---

## Rust — rustdoc / `///` Comments

```rust
/// Calculate the root mean squared error between two slices.
///
/// Both slices must have the same length and must not be empty.
///
/// # Arguments
///
/// * `predictions` - Predicted values.
/// * `targets` - Ground-truth values.
///
/// # Returns
///
/// The RMSE as an `f64`.
///
/// # Panics
///
/// Panics if the slices have different lengths.
///
/// # Example
///
/// ```
/// use mylib::calc_rmse;
/// let rmse = calc_rmse(&[2.0, 3.0], &[2.5, 2.5]);
/// assert!((rmse - 0.5).abs() < 1e-10);
/// ```
pub fn calc_rmse(predictions: &[f64], targets: &[f64]) -> f64 {
    assert_eq!(predictions.len(), targets.len(), "slice length mismatch");
    let sum: f64 = predictions.iter()
        .zip(targets)
        .map(|(p, t)| (p - t).powi(2))
        .sum();
    (sum / predictions.len() as f64).sqrt()
}
```

---

## Go — godoc / `//` Comments

```go
// Package calc provides numeric calculation utilities.
package calc

// Rmse calculates the root mean squared error between predictions and targets.
//
// Both slices must have equal non-zero length. Returns an error if the slices
// are empty or have mismatched lengths.
//
// Example:
//
//	rmse, err := calc.Rmse([]float64{2.0, 3.0}, []float64{2.5, 2.5})
func Rmse(predictions, targets []float64) (float64, error) {
	if len(predictions) == 0 || len(targets) == 0 {
		return 0, errors.New("slices must not be empty")
	}
	if len(predictions) != len(targets) {
		return 0, errors.New("slice length mismatch")
	}
	var sum float64
	for i := range predictions {
		diff := predictions[i] - targets[i]
		sum += diff * diff
	}
	return math.Sqrt(sum / float64(len(predictions))), nil
}
```
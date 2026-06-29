---
language: python
tags: [numpy, array, linear-algebra, python]
title: NumPy Basics
description: Array creation, broadcasting, reshaping, linear algebra, random numbers, and universal functions
source: pattern
---

```python
import numpy as np

# ---------------------------------------------------------------------------
# Array creation
# ---------------------------------------------------------------------------

# From a list
a = np.array([1, 2, 3, 4, 5])
b = np.array([[1, 2, 3], [4, 5, 6]])  # 2D array

# Zeros, ones, empty, eye
zeros = np.zeros((3, 4))               # 3×4 matrix of zeros
ones = np.ones((2, 3))                 # 2×3 matrix of ones
empty = np.empty((3, 3))               # Uninitialized (random values)
identity = np.eye(4)                   # 4×4 identity matrix

# Ranges
arange = np.arange(0, 10, 2)           # [0, 2, 4, 6, 8]
linspace = np.linspace(0, 1, 5)        # [0.0, 0.25, 0.5, 0.75, 1.0]

# Filled with a constant
full = np.full((2, 3), 7)             # 2×3 array all 7s

# Like another array
c = np.ones_like(b)                    # Same shape as b, filled with 1

# ---------------------------------------------------------------------------
# Array attributes
# ---------------------------------------------------------------------------

print(f"shape: {b.shape}")      # (2, 3)
print(f"ndim: {b.ndim}")        # 2
print(f"size: {b.size}")        # 6
print(f"dtype: {b.dtype}")      # int64
print(f"itemsize: {b.itemsize}")  # bytes per element

# ---------------------------------------------------------------------------
# Indexing and slicing
# ---------------------------------------------------------------------------

arr = np.array([[1, 2, 3, 4], [5, 6, 7, 8], [9, 10, 11, 12]])

print(arr[0, 0])      # 1 — first row, first col
print(arr[1, :])      # [5 6 7 8] — second row, all cols
print(arr[:, 1])      # [2 6 10] — all rows, second col
print(arr[0:2, 1:3])  # [[2 3] [6 7]] — submatrix

# Boolean indexing
mask = arr > 5
print(arr[mask])      # [6 7 8 9 10 11 12]

# Fancy indexing (integer arrays)
indices = np.array([0, 2])
print(arr[indices])   # Rows 0 and 2

# ---------------------------------------------------------------------------
# Reshaping
# ---------------------------------------------------------------------------

flat = np.arange(12)
print(flat.reshape(3, 4))               # 3×4 matrix
print(flat.reshape(2, 2, 3))            # 3D array
print(flat.reshape(-1, 4))              # Infer row count: (3, 4)

# Flatten / ravel
print(flat.reshape(3, 4).flatten())     # Returns copy
print(flat.reshape(3, 4).ravel())       # Returns view (if possible)

# Transpose
m = np.array([[1, 2], [3, 4]])
print(m.T)  # [[1 3] [2 4]]

# ---------------------------------------------------------------------------
# Broadcasting
# ---------------------------------------------------------------------------

# (3, 1) + (1, 4) → (3, 4) via broadcasting
a = np.array([[1], [2], [3]])     # shape (3, 1)
b = np.array([10, 20, 30, 40])    # shape (4,) → broadcast to (1, 4)
print(a + b)  # Result shape (3, 4)

# Scalar broadcasts to all elements
print(arr + 100)

# Column-wise operation
data = np.random.randn(4, 3)
col_mean = data.mean(axis=0)       # shape (3,)
centered = data - col_mean         # (4, 3) - (3,) → works via broadcasting

# ---------------------------------------------------------------------------
# Universal functions (ufuncs)
# ---------------------------------------------------------------------------

x = np.array([1, 2, 3, 4, 5])

print(np.sqrt(x))      # Square root
print(np.exp(x))       # e^x
print(np.log(x))       # Natural log
print(np.sin(x))       # Sine
print(np.abs([-1, -2, 3]))  # Absolute value
print(np.power(x, 2))  # x^2

# Where — conditional selection
print(np.where(x > 3, x, 0))  # [0 0 0 4 5]

# Clip — bound values
print(np.clip(x, 2, 4))  # [2 2 3 4 4]

# ---------------------------------------------------------------------------
# Linear algebra
# ---------------------------------------------------------------------------

A = np.array([[1, 2], [3, 4]])
B = np.array([[5, 6], [7, 8]])

# Matrix multiplication (dot product)
print(np.dot(A, B))      # [[19 22] [43 50]]
print(A @ B)             # Same, using @ operator

# Vector dot product
v = np.array([1, 2, 3])
w = np.array([4, 5, 6])
print(np.dot(v, w))      # 32

# Determinant
print(np.linalg.det(A))  # -2.0

# Matrix inverse
print(np.linalg.inv(A))  # [[-2.  1.] [1.5 -0.5]]

# Solve linear system: A x = b
A = np.array([[3, 1], [1, 2]])
b = np.array([9, 8])
x = np.linalg.solve(A, b)
print(x)  # [2. 3.] — solution

# Eigenvalues and eigenvectors
eigvals, eigvecs = np.linalg.eig(A)
print(eigvals)
print(eigvecs)

# SVD
U, S, Vt = np.linalg.svd(A)

# ---------------------------------------------------------------------------
# Random numbers
# ---------------------------------------------------------------------------

rng = np.random.default_rng(seed=42)  # Modern RNG

print(rng.random((3, 3)))             # Uniform [0, 1)
print(rng.normal(0, 1, 1000))        # Normal (mean=0, std=1)
print(rng.integers(0, 100, 10))      # Random integers
print(rng.choice(["a", "b", "c"], size=5, p=[0.5, 0.3, 0.2]))  # Weighted
print(rng.shuffle(np.arange(10)))     # Shuffle in-place

# Old-style (still common)
# np.random.rand(3, 3)
# np.random.randn(1000)
# np.random.randint(0, 100, 10)
```
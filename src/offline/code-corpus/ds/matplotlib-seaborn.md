---
language: python
tags: [matplotlib, seaborn, visualization, plotting]
title: Matplotlib and Seaborn
description: Basic plots (line, scatter, bar, histogram), subplots, figure/axis, seaborn style themes, and saving figures
source: pattern
---

```python
import matplotlib.pyplot as plt
import seaborn as sns
import numpy as np
import pandas as pd

# ---------------------------------------------------------------------------
# Seaborn style themes
# ---------------------------------------------------------------------------

# Available themes: "darkgrid", "whitegrid", "dark", "white", "ticks"
sns.set_theme(style="whitegrid", palette="muted", font_scale=1.1)

# Or use matplotlib styles directly
# plt.style.use("ggplot")
# plt.style.use("seaborn-v0_8")

# ---------------------------------------------------------------------------
# Figure and axis — the core API
# ---------------------------------------------------------------------------

# Create figure + single axis
fig, ax = plt.subplots(figsize=(8, 5))

# Create figure + multiple subplots
fig, axes = plt.subplots(2, 2, figsize=(10, 8))
# axes is a 2×2 array: axes[0,0], axes[0,1], axes[1,0], axes[1,1]

# ---------------------------------------------------------------------------
# Line plot
# ---------------------------------------------------------------------------

x = np.linspace(0, 10, 100)
y1 = np.sin(x)
y2 = np.cos(x)

fig, ax = plt.subplots(figsize=(8, 4))
ax.plot(x, y1, label="sin(x)", color="blue", linewidth=2, linestyle="-")
ax.plot(x, y2, label="cos(x)", color="red", linewidth=2, linestyle="--")
ax.set_xlabel("x")
ax.set_ylabel("y")
ax.set_title("Trigonometric Functions")
ax.legend()
ax.grid(True, alpha=0.3)
plt.tight_layout()
plt.show()

# ---------------------------------------------------------------------------
# Scatter plot
# ---------------------------------------------------------------------------

n = 100
x = np.random.randn(n)
y = 2 * x + np.random.randn(n) * 0.5
colors = np.random.rand(n)
sizes = np.random.uniform(20, 200, n)

fig, ax = plt.subplots(figsize=(7, 5))
scatter = ax.scatter(x, y, c=colors, s=sizes, alpha=0.7, cmap="viridis")
ax.set_xlabel("X")
ax.set_ylabel("Y")
ax.set_title("Scatter Plot")
fig.colorbar(scatter, ax=ax, label="Color value")
plt.tight_layout()
plt.show()

# Seaborn scatter
df = pd.DataFrame({"x": x, "y": y, "group": np.random.choice(["A", "B"], n)})
sns.scatterplot(data=df, x="x", y="y", hue="group", style="group", s=80)

# ---------------------------------------------------------------------------
# Bar plot
# ---------------------------------------------------------------------------

categories = ["A", "B", "C", "D", "E"]
values = [23, 45, 56, 78, 32]

fig, ax = plt.subplots(figsize=(7, 4))
bars = ax.bar(categories, values, color="steelblue", edgecolor="black")
ax.set_xlabel("Category")
ax.set_ylabel("Value")
ax.set_title("Bar Plot")
ax.bar_label(bars)  # Add value labels on top
plt.tight_layout()
plt.show()

# Horizontal bar
# ax.barh(categories, values)

# Seaborn bar plot (with error bars)
sns.barplot(data=df, x="group", y="y")

# ---------------------------------------------------------------------------
# Histogram
# ---------------------------------------------------------------------------

data = np.random.randn(1000)

fig, ax = plt.subplots(figsize=(7, 4))
ax.hist(data, bins=30, density=True, alpha=0.7, color="purple", edgecolor="black")
ax.set_xlabel("Value")
ax.set_ylabel("Density")
ax.set_title("Histogram with Density")

# Overlay a KDE
from scipy.stats import gaussian_kde
kde = gaussian_kde(data)
x_kde = np.linspace(data.min(), data.max(), 200)
ax.plot(x_kde, kde(x_kde), color="red", linewidth=2)
plt.tight_layout()
plt.show()

# Seaborn histogram + KDE
sns.histplot(data, bins=30, kde=True)

# ---------------------------------------------------------------------------
# Subplots
# ---------------------------------------------------------------------------

fig, axes = plt.subplots(2, 2, figsize=(10, 8))

# Line plot
axes[0, 0].plot(x, np.sin(x), color="blue")
axes[0, 0].set_title("sin(x)")

# Scatter
axes[0, 1].scatter(np.random.randn(50), np.random.randn(50), alpha=0.6)
axes[0, 1].set_title("Random Scatter")

# Histogram
axes[1, 0].hist(np.random.randn(500), bins=20, color="green", alpha=0.7)
axes[1, 0].set_title("Histogram")

# Bar
axes[1, 1].bar(["A", "B", "C"], [10, 20, 15], color="orange")
axes[1, 1].set_title("Bar")

plt.tight_layout()
plt.show()

# ---------------------------------------------------------------------------
# Seaborn convenience plots
# ---------------------------------------------------------------------------

# Load built-in dataset
tips = sns.load_dataset("tips")

# Box plot
sns.boxplot(data=tips, x="day", y="total_bill", hue="sex")

# Violin plot
sns.violinplot(data=tips, x="day", y="total_bill", hue="sex", split=True)

# Pair plot (scatter matrix)
# sns.pairplot(tips, hue="sex", diag_kind="kde")

# Heatmap (correlation matrix)
corr = tips.select_dtypes(include=[np.number]).corr()
sns.heatmap(corr, annot=True, cmap="coolwarm", fmt=".2f", linewidths=0.5)

# Joint plot (scatter + histograms)
# sns.jointplot(data=tips, x="total_bill", y="tip", kind="scatter")

# ---------------------------------------------------------------------------
# Saving figures
# ---------------------------------------------------------------------------

fig, ax = plt.subplots(figsize=(6, 4))
ax.plot(x, np.sin(x))
ax.set_title("Save Example")

# Save as PNG (high DPI for publication)
plt.savefig("plot.png", dpi=300, bbox_inches="tight")

# Save as PDF (vector)
plt.savefig("plot.pdf", bbox_inches="tight")

# Save as SVG (vector, editable)
plt.savefig("plot.svg", bbox_inches="tight")

# Close figure to free memory
plt.close(fig)

# ---------------------------------------------------------------------------
# Customization tips
# ---------------------------------------------------------------------------

fig, ax = plt.subplots(figsize=(8, 5))
ax.plot(x, y1, label="sin", color="#2E86AB")
ax.plot(x, y2, label="cos", color="#A23B72")

# Axis limits
ax.set_xlim(0, 2 * np.pi)
ax.set_ylim(-1.5, 1.5)

# Ticks
ax.set_xticks([0, np.pi/2, np.pi, 3*np.pi/2, 2*np.pi])
ax.set_xticklabels(["0", "π/2", "π", "3π/2", "2π"])

# Grid and spines
ax.spines["top"].set_visible(False)
ax.spines["right"].set_visible(False)

# Annotations
ax.annotate("Peak", xy=(np.pi/2, 1), xytext=(np.pi/2, 1.2),
            arrowprops=dict(arrowstyle="->", color="black"))

plt.tight_layout()
plt.show()
```
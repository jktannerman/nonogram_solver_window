# Nonogram Solver

A Python desktop application for creating and solving [nonograms](https://en.wikipedia.org/wiki/Nonogram) (also known as Picross or Griddlers).

## Features

- **Interactive GUI** — enter grid dimensions, input row/column clues, and paint cells by clicking.
- **Solver engine** *(in progress)* — logical deduction followed by recursive trial-and-error, returning all unique solutions.

## Requirements

- Python 3.13+
- No third-party packages — uses only the standard library (`tkinter`).

## Usage

```
py -3.13 main.py
```

1. Enter the number of rows and columns, then click **Generate Grid**.
2. Enter clue numbers into the boxes above each column and to the left of each row.
   - Column clue boxes stack top-to-bottom; navigate with **Down**.
   - Row clue boxes run left-to-right; navigate with **Right**.
   - Both sequences wrap: the last column box moves focus to the first row box, and the last row box wraps back to the first column box.
3. Click any grid square to cycle its state: **grey** (unknown) → **black** (filled) → **white** (empty) → grey.
4. Click **New Grid** to return to the size-entry screen.

## Project structure

```
nonogram_solver/
├── main.py      # tkinter GUI — grid input and visualisation
└── solver.py    # solver logic (entry point: solve())
```

## Solver design (`solver.py`)

The public function is:

```python
solve(row_clues, col_clues, initial_board=None) -> list[Board]
```

It returns every unique complete solution as a list of 2-D integer grids using the same cell convention as the GUI (`0` = unknown, `1` = black, `2` = white).

Internally the solver proceeds in two stages:

### Stage 1 — logical deduction

`_deduce` sweeps every row and column in a loop, applying `_deduce_line` to each until no further progress is made. Row and column sweeps interleave, so a deduction in one direction can immediately unlock new deductions in the other.

`_deduce_line` applies a sequence of tactics:

| Tactic | Description |
|---|---|
| `_tactic_overlap` | Left-pack and right-pack all blocks; cells covered in both packings are definitely BLACK; cells outside all block ranges in both are definitely WHITE. |
| `_tactic_completion` | Once the count of BLACK cells equals the clue sum, all remaining unknowns become WHITE. |
| `_tactic_edge_anchoring` | Extend or cap blocks anchored against line boundaries or known WHITE cells. |
| `_line_is_feasible` | Fast structural check (minimum span, run lengths, cell counts) used before and after the other tactics. |

### Stage 2 — trial and error

If deduction alone cannot fully determine the board, the solver picks an unknown cell, hypothesises BLACK then WHITE, and recurses. Each branch independently re-runs Stage 1, which often cascades into many additional deductions. Contradictions are caught early and prune the search tree immediately. All unique solutions are collected via a hash-based deduplication set.

> **Status:** The overall recursive structure and tactic dispatch are implemented. The individual tactic bodies are stubs and have not yet been filled in.

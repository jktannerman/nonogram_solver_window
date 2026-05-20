# Nonogram Solver

A Python desktop application for creating and solving [nonograms](https://en.wikipedia.org/wiki/Nonogram) (also known as Picross or Griddlers).

## Features

- **Interactive GUI** — enter grid dimensions, input row/column clues, and paint cells by clicking.
- **Solver engine** — logical deduction followed by recursive trial-and-error, returning all unique solutions.

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
├── main.py         # tkinter GUI — grid input and visualisation
├── solver.py       # solver logic (entry point: solve())
└── test_solver.py  # pytest tests for deduction and solve()
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

`_deduce_line` delegates to a single **brute-force tactic**:

1. `_all_valid_arrangements` enumerates every complete BLACK/WHITE assignment for the line that is consistent with the clue and any already-fixed cells, using a backtracking search with early pruning.
2. `_tactic_brute_force` intersects those arrangements: any cell that is BLACK in every valid arrangement is marked BLACK; any cell that is WHITE in every valid arrangement is marked WHITE. If no valid arrangement exists the line is a contradiction.

### Stage 2 — trial and error

If deduction alone cannot fully determine the board, the solver picks an unknown cell, hypothesises BLACK then WHITE, and recurses. Each branch independently re-runs Stage 1, which often cascades into many additional deductions. Contradictions are caught early and prune the search tree immediately. All unique solutions are collected via a hash-based deduplication set.

## Tests

```
py -3.13 -m pytest nonogram_solver/test_solver.py -v
```

`test_solver.py` contains two parameterised test lists that are easy to extend:

- `DEDUCE_LINE_CASES` — unit tests for `_deduce_line` covering overlap deductions, edge anchoring, partially-filled lines, and contradictions.
- `SOLVE_CASES` — end-to-end tests for `solve()`, including puzzles with multiple solutions.

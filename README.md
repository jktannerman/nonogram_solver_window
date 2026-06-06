# Nonogram Solver

A Python desktop application for creating and solving [nonograms](https://en.wikipedia.org/wiki/Nonogram) (also known as Picross or Griddlers).

## Features

- **Interactive GUI** — enter grid dimensions, input row/column clues, and paint cells by clicking.
- **Solver engine** — logical deduction followed by recursive trial-and-error, returning all unique solutions.
- **Solution browser** — step through all solutions with Previous / Next buttons.
- **Adaptive layout** — the window opens maximised and rescales both grids to fill the available space whenever the window is resized.

## Requirements

- Python 3.13+
- No third-party packages — uses only the standard library (`tkinter`).

## Usage

```
py -3.13 main.py
```

1. Enter the number of rows and columns (1–50 each; defaults are 9 rows and 12 columns), then click **Generate Grid** or press **Enter**.
2. Enter clue numbers into the boxes above each column and to the left of each row.  Each box holds one block length; fill left-to-right for rows and top-to-bottom for columns.
   - Navigate clue boxes with the arrow keys:
     - **Right / Left** move between boxes within a row clue; **Down / Up** jump to the start of the next / previous row.
     - **Down / Up** move between boxes within a column clue; **Right / Left** jump to the top of the next / previous column.
   - **Enter** advances to the next row (in a row clue) or the next column (in a column clue).
   - Typing a digit automatically advances to the next box within the same row or column clue.
   - **Tab** cycles through all row boxes then all column boxes, wrapping back to the start.
3. Click any grid square to cycle its state: **grey** (unknown) → **dark grey** (filled) → **white** (empty) → grey.
4. Click **Solve**. Solutions appear in the lower half of the window.
   - Use **< Previous** and **Next >** to step through multiple solutions.
5. Click **New Grid** to return to the size-entry screen.

## Layout

The window is divided into two sections:

- **Top section** — the input canvas, containing the clue entry boxes (to the left of and above the grid) plus the interactive grid cells.  **New Grid** and **Solve** buttons sit in a panel to the right of this canvas.
- **Bottom section** — a read-only canvas showing the current solution grid (cells only, no clue boxes).  **< Previous**, a solution counter label, and **Next >** sit in a panel to the right of this canvas.

Both grids use the same cell size, which is computed at startup (and recomputed on resize) so that the input canvas fits within the window without overflow.  Because the input canvas includes rows of column-clue boxes above the grid and columns of row-clue boxes to its left, it is larger than the solution canvas.

## Logging

The application writes structured JSON logs to `nonogram.log` in the project directory (DEBUG level and above).

## Project structure

```
nonogram_solver/
├── main.py         # tkinter GUI — grid input, visualisation, solution browser
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

If deduction alone cannot fully determine the board, the solver picks the first unknown cell in reading order, hypothesises BLACK then WHITE, and recurses. Each branch independently re-runs Stage 1, which often cascades into many additional deductions. Contradictions are caught early and prune the search tree immediately. All unique solutions are collected via a hash-based deduplication set.

## Tests

```
py -3.13 -m pytest nonogram_solver/test_solver.py -v
```

`test_solver.py` contains two parameterised test lists that are easy to extend:

- `DEDUCE_LINE_CASES` — unit tests for `_deduce_line` covering overlap deductions, edge anchoring, partially-filled lines, and contradictions.
- `SOLVE_CASES` — end-to-end tests for `solve()`, including puzzles with multiple solutions.

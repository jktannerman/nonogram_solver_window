"""Nonogram solver logic.

Cell state convention (matches the GUI):
    UNKNOWN = 0   -- not yet determined
    BLACK   = 1   -- confirmed filled
    WHITE   = 2   -- confirmed empty

A Board is a 2-D list indexed [row][col].
"""

from __future__ import annotations
import copy

# Cell states
UNKNOWN = 0
BLACK   = 1
WHITE   = 2

Board = list[list[int]]


# ---------------------------------------------------------------------------
# Public entry point
# ---------------------------------------------------------------------------

def solve(
    row_clues: list[list[int]],
    col_clues: list[list[int]],
    initial_board: Board | None = None,
) -> list[Board]:
    """Solve a nonogram and return every unique solution.

    Args:
        row_clues: Row constraints, e.g. [[3], [1, 1], [2]] for a 3-row grid.
        col_clues: Column constraints in the same format.
        initial_board: Optional partially-filled starting state.  If None a
            blank board is used.  Pre-filled BLACK / WHITE cells are treated
            as fixed givens.

    Returns:
        A list of complete boards (no UNKNOWN cells) that satisfy all
        constraints.  Each board is a distinct object.  Returns an empty list
        if no solution exists.
    """
    rows = len(row_clues)
    cols = len(col_clues)

    if initial_board is not None:
        board: Board = copy.deepcopy(initial_board)
    else:
        board = [[UNKNOWN] * cols for _ in range(rows)]

    found: list[Board] = []
    seen: set[tuple[tuple[int, ...], ...]] = set()

    _solve_recursive(board, row_clues, col_clues, found, seen)
    return found


# ---------------------------------------------------------------------------
# Recursive solver
# ---------------------------------------------------------------------------

def _solve_recursive(
    board: Board,
    row_clues: list[list[int]],
    col_clues: list[list[int]],
    found: list[Board],
    seen: set[tuple[tuple[int, ...], ...]],
) -> None:
    """Recursive kernel: deduce, then branch on an unknown cell if needed.

    Args:
        board: Current board state (will be deep-copied before mutation).
        row_clues: Row constraints.
        col_clues: Column constraints.
        found: Accumulator for discovered solutions.
        seen: Set of already-recorded board keys for deduplication.
    """
    # Work on a private copy so sibling branches are independent.
    board = copy.deepcopy(board)

    # ------------------------------------------------------------------
    # Stage 1 — logical deduction
    # Apply deduction rules repeatedly until the board stops changing or
    # a contradiction is found.  Each iteration sweeps every row then
    # every column.
    # ------------------------------------------------------------------
    if not _deduce(board, row_clues, col_clues):
        return  # dead end — current path violates a constraint

    # ------------------------------------------------------------------
    # Check for completion
    # ------------------------------------------------------------------
    if _is_complete(board):
        key = _board_key(board)
        if key not in seen:
            seen.add(key)
            found.append(copy.deepcopy(board))
        return

    # ------------------------------------------------------------------
    # Stage 2 — trial and error
    # The board still has UNKNOWN cells that logic alone cannot resolve.
    # Pick one cell, hypothesise each possible value, and recurse.
    # Each branch independently re-runs Stage 1, which often cascades
    # into many additional deductions before the next branch point.
    # Contradictions are caught by _deduce returning False, pruning that
    # subtree immediately.
    # ------------------------------------------------------------------
    r, c = _pick_branch_cell(board)

    for value in (BLACK, WHITE):
        branch = copy.deepcopy(board)
        branch[r][c] = value
        _solve_recursive(branch, row_clues, col_clues, found, seen)


# ---------------------------------------------------------------------------
# Stage 1 — deduction driver
# ---------------------------------------------------------------------------

def _deduce(
    board: Board,
    row_clues: list[list[int]],
    col_clues: list[list[int]],
) -> bool:
    """Apply all deduction tactics until stable.

    Sweeps rows then columns repeatedly.  Each sweep may unlock further
    deductions in the perpendicular direction, so the loop continues until
    a full sweep produces no new information.

    Args:
        board: Modified in place.
        row_clues: Row constraints.
        col_clues: Column constraints.

    Returns:
        False if a contradiction is detected (board state is unsolvable),
        True otherwise.
    """
    changed = True
    while changed:
        changed = False

        for r, clue in enumerate(row_clues):
            updated = _deduce_line(board[r], clue)
            if updated is None:
                return False
            if updated != board[r]:
                board[r] = updated
                changed = True

        cols = len(col_clues)
        rows = len(board)
        for c, clue in enumerate(col_clues):
            col = [board[r][c] for r in range(rows)]
            updated = _deduce_line(col, clue)
            if updated is None:
                return False
            for r in range(rows):
                if board[r][c] != updated[r]:
                    board[r][c] = updated[r]
                    changed = True

    return True


# ---------------------------------------------------------------------------
# Line-level deduction
# ---------------------------------------------------------------------------

def _deduce_line(line: list[int], clue: list[int]) -> list[int] | None:
    """Apply brute-force deduction to a single row or column.

    Args:
        line: Current cell states for the line (not mutated).
        clue: Block lengths for this line.

    Returns:
        Updated line, or None if the line state contradicts the clue.
    """
    line = list(line)

    # Empty clue: every cell must be white.
    if not clue or clue == [0]:
        if BLACK in line:
            return None
        return [WHITE] * len(line)

    return _tactic_brute_force(line, clue)


# ---------------------------------------------------------------------------
# Brute-force tactic
# ---------------------------------------------------------------------------

def _all_valid_arrangements(line: list[int], clue: list[int]) -> list[list[int]]:
    """Generate every complete arrangement of blocks consistent with the line.

    Args:
        line: Current cell states (UNKNOWN / BLACK / WHITE).
        clue: Ordered list of block lengths.

    Returns:
        Every complete arrangement (all cells BLACK or WHITE) that places the
        blocks exactly as specified and agrees with all fixed cells in line.
    """
    n = len(line)
    results: list[list[int]] = []

    def backtrack(block_idx: int, pos: int, arr: list[int]) -> None:
        if block_idx == len(clue):
            # All remaining cells must be WHITE.
            for i in range(pos, n):
                if line[i] == BLACK:
                    return
            results.append(arr + [WHITE] * (n - pos))
            return

        block_len = clue[block_idx]
        is_last = block_idx + 1 == len(clue)
        # Minimum space required after this block's separator for all remaining blocks.
        remaining_min = sum(clue[block_idx + 1:]) + len(clue[block_idx + 1:])
        max_start = n - block_len - remaining_min

        for start in range(pos, max_start + 1):
            # Each iteration adds one cell to the pre-gap; if it's BLACK the
            # gap can never be all-WHITE for this or any larger start.
            if start > pos and line[start - 1] == BLACK:
                break

            # Block cells must not be WHITE.
            if any(line[i] == WHITE for i in range(start, start + block_len)):
                continue

            # The mandatory separator after a non-last block must not be BLACK.
            if not is_last and line[start + block_len] == BLACK:
                continue

            pre_gap = [WHITE] * (start - pos)
            block_cells = [BLACK] * block_len
            new_arr = arr + pre_gap + block_cells

            if is_last:
                next_pos = start + block_len
            else:
                new_arr = new_arr + [WHITE]  # separator
                next_pos = start + block_len + 1

            backtrack(block_idx + 1, next_pos, new_arr)

    backtrack(0, 0, [])
    return results


def _tactic_brute_force(line: list[int], clue: list[int]) -> list[int] | None:
    """Determine every cell forced BLACK or WHITE across all valid arrangements.

    Args:
        line: Current cell states.
        clue: Block lengths.

    Returns:
        Updated line with newly-determined cells filled in, or None if no
        valid arrangement exists (contradiction detected).
    """
    arrangements = _all_valid_arrangements(line, clue)
    if not arrangements:
        return None

    result = list(line)
    for i in range(len(line)):
        if result[i] != UNKNOWN:
            continue
        values = {arr[i] for arr in arrangements}
        if len(values) == 1:
            result[i] = next(iter(values))

    return result


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _is_complete(board: Board) -> bool:
    """Return True if every cell is BLACK or WHITE (no UNKNOWN cells remain)."""
    return all(cell != UNKNOWN for row in board for cell in row)


def _pick_branch_cell(board: Board) -> tuple[int, int]:
    """Choose an UNKNOWN cell to branch on during trial-and-error.

    A good heuristic is to pick the cell whose row or column has the fewest
    remaining valid arrangements (most constrained), as this minimises the
    branching factor.  For now, returns the first UNKNOWN cell in reading
    order, which is correct but not optimally efficient.
    """
    for r, row in enumerate(board):
        for c, cell in enumerate(row):
            if cell == UNKNOWN:
                return r, c
    raise ValueError("_pick_branch_cell called on a complete board")


def _board_key(board: Board) -> tuple[tuple[int, ...], ...]:
    """Return a hashable, immutable representation of a board for deduplication."""
    return tuple(tuple(row) for row in board)

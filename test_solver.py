"""Tests for nonogram solver deduction logic.

To add a new test case, append a tuple to the relevant CASES list:
    (line, clue, expected)
where expected is the updated line, or None for a contradiction.

Cell state shorthands used in this file:
    U = UNKNOWN (0)
    B = BLACK   (1)
    W = WHITE   (2)
"""

import pytest
from solver import _deduce_line, solve, UNKNOWN as U, BLACK as B, WHITE as W


# ---------------------------------------------------------------------------
# _deduce_line test cases
# Each entry: (line, clue, expected_result)
#   expected_result = None  →  contradiction expected
# ---------------------------------------------------------------------------

DEDUCE_LINE_CASES = [
    # --- Empty / trivial clues ---
    pytest.param([U, U, U],   [],    [W, W, W],       id="empty_clue"),
    pytest.param([U, U, U],   [0],   [W, W, W],       id="zero_clue"),
    pytest.param([B, U, U],   [],    None,            id="empty_clue_contradiction"),

    # --- Single block: overlap deductions ---
    pytest.param([U, U, U, U, U], [3], [U, U, B, U, U], id="single_block_overlap_5c3"),
    pytest.param([U, U, U],       [3], [B, B, B],       id="single_block_fills_line"),
    pytest.param([U, U, U, U],    [4], [B, B, B, B],    id="single_block_fills_line_4"),
    pytest.param([U, U, U, U, U], [5], [B, B, B, B, B], id="single_block_fills_line_5"),
    pytest.param([U, U, U, U, U], [1], [U, U, U, U, U], id="single_block_no_deduction"),

    # --- Single block: whites forced at edges ---
    pytest.param([U, U, U, U, U], [4], [U, B, B, B, U],  id="single_block_4_forces_whites"),
    pytest.param([U, U, U, U],    [3], [U, B, B, U],     id="single_block_3_in_4"),

    # --- Multiple blocks ---
    pytest.param([U, U, U, U, U],       [1, 1], [U, U, U, U, U],       id="two_singles_no_deduction"),
    pytest.param([U, U, U, U, U, U],    [2, 2], [U, B, U, U, B, U],    id="two_2s_overlap"),
    pytest.param([U, U, U, U, U, U, U], [3, 2], [U, B, B, U, U, B, U], id="3_and_2_overlap"),
    pytest.param([U, U, U, U, U, U],    [2, 1], [U, U, U, U, U, U],    id="2_and_1_no_deduction"),

    # --- Partially filled lines ---
    pytest.param([B, U, U, U, U], [3], [B, B, B, W, W],   id="anchored_block_at_start"),
    pytest.param([U, U, U, U, B], [3], [W, W, B, B, B],   id="anchored_block_at_end"),
    pytest.param([U, B, U, U, U], [3], [U, B, B, U, W],   id="partial_block_mid"),
    pytest.param([W, U, U, U, U], [3], [W, U, B, B, U],   id="white_at_start_shifts_block"),

    # --- Already fully determined lines ---
    pytest.param([B, B, B, W, W], [3],    [B, B, B, W, W], id="already_solved_row"),
    pytest.param([W, B, W, B, W], [1, 1], [W, B, W, B, W], id="already_solved_alternating"),

    # --- Contradictions ---
    pytest.param([U, U],          [3],    None, id="block_too_long"),
    pytest.param([B, W, B, W, B], [3],    None, id="no_valid_placement"),
    pytest.param([W, W, W],       [1],    None, id="all_white_but_need_black"),
    pytest.param([B, B, U, B, B], [1, 1], None, id="runs_exceed_clue"),
]


@pytest.mark.parametrize("line, clue, expected", DEDUCE_LINE_CASES)
def test_deduce_line(line: list[int], clue: list[int], expected: list[int] | None) -> None:
    """_deduce_line returns the expected updated line, or None for contradictions."""
    result = _deduce_line(line, clue)
    assert result == expected


# ---------------------------------------------------------------------------
# End-to-end solve() tests
# Each entry: (row_clues, col_clues, expected_solutions)
# expected_solutions is a list of boards (each board = list of rows).
# ---------------------------------------------------------------------------

SOLVE_CASES = [
    pytest.param(
        [[1], [1]],
        [[0], [0], [2]],
        [
            [[W, W, B],
             [W, W, B]],
        ],
        id="2x3_trivial",
    ),
    pytest.param(
        [[3], [1, 1], [3]],
        [[3], [1, 1], [3]],
        [
            [[B, B, B],
             [B, W, B],
             [B, B, B]],
        ],
        id="3x3_frame",
    ),
    pytest.param(
        [[1], [1]],
        [[1], [1]],
        [
            [[B, W], [W, B]],
            [[W, B], [B, W]],
        ],
        id="2x2_two_solutions",
    ),
]


@pytest.mark.parametrize("row_clues, col_clues, expected_solutions", SOLVE_CASES)
def test_solve(
    row_clues: list[list[int]],
    col_clues: list[list[int]],
    expected_solutions: list[list[list[int]]],
) -> None:
    """solve() returns exactly the expected set of solutions."""
    results = solve(row_clues, col_clues)

    def board_key(b: list[list[int]]) -> tuple[tuple[int, ...], ...]:
        return tuple(tuple(r) for r in b)

    assert {board_key(b) for b in results} == {board_key(b) for b in expected_solutions}

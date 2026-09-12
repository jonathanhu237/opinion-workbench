"""Closed diagnostic reasons for a failed product search run.

The search run status describes the durable lifecycle (active, successful or
terminal).  These values describe the narrower cause of the legacy
``structure_changed`` status.  Keep this module free of API, repository and
worker imports so every layer can use the same constrained vocabulary without
creating an ownership cycle.
"""

from typing import Literal, get_args

SearchFailureReason = Literal[
    "page_state_unrecognized",
    "search_context_unavailable",
    "search_response_incompatible",
    "search_results_incompatible",
    "search_pagination_incompatible",
]

SEARCH_FAILURE_REASONS = frozenset(get_args(SearchFailureReason))


def is_search_failure_reason(value: object) -> bool:
    """Return whether *value* is one of the stable persisted reason codes."""

    return type(value) is str and value in SEARCH_FAILURE_REASONS

"""One eligibility definition shared by preview counts and atomic admission."""

from longtian_api.schemas.report_generations import GenerationEligibility

LIBRARY_FROM = """FROM content_analysis_claims cl
    LEFT JOIN content_analysis_attempts a ON a.id=cl.latest_attempt_id"""
INACTIVE = "cl.active_job_id IS NULL AND cl.active_legacy_summary_id IS NULL"
PENDING = "cl.first_attempt_id IS NULL AND cl.legacy_state IS NULL"
RECOVERABLE = """(a.status IN
    ('failed','input_incomplete','unsupported','cancelled','interrupted')
    OR (a.id IS NULL AND cl.legacy_state='legacy_attempted'))"""


def eligibility(connection):
    row = connection.execute(f"""SELECT
        COALESCE(SUM(({INACTIVE}) AND ({PENDING})),0) AS pending,
        COALESCE(SUM(({INACTIVE}) AND ({RECOVERABLE})),0) AS failed,
        COALESCE(SUM(NOT ({INACTIVE})),0) AS active {LIBRARY_FROM}""").fetchone()
    return GenerationEligibility(**dict(row))


def select_library(connection):
    return [
        row[0]
        for row in connection.execute(
            f"""SELECT cl.content_id
        {LIBRARY_FROM} WHERE ({INACTIVE}) AND
        (({PENDING}) OR ({RECOVERABLE})) ORDER BY cl.content_id""",
        )
    ]

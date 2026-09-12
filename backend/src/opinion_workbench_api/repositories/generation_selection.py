"""One eligibility definition shared by preview counts and atomic admission."""

from opinion_workbench_api.schemas.report_generations import GenerationEligibility

LIBRARY_FROM = """FROM content_analysis_claims cl
    LEFT JOIN content_analysis_attempts a ON a.id=cl.latest_attempt_id"""
INACTIVE = """cl.active_job_id IS NULL AND cl.active_legacy_summary_id IS NULL
    AND NOT EXISTS (
        SELECT 1 FROM topic_report_sources s
        JOIN topic_report_runs r ON r.id=s.report_id
        WHERE s.content_id=cl.content_id
            AND r.status IN ('queued','judging','composing')
    ) AND NOT EXISTS (
        SELECT 1 FROM content_analysis_attempts ga
        JOIN report_generations g ON g.analysis_job_id=ga.job_id
        WHERE ga.content_id=cl.content_id AND g.finished_at IS NULL
    )"""
# A completed report's verified root membership is exactly its cited sources,
# including sources carried through nested overview sections. Selection alone,
# an irrelevant judgment, or a completed leaf in a failed report does not count.
UNREPORTED = """NOT EXISTS (
    SELECT 1 FROM topic_report_sources s
    JOIN topic_report_runs r ON r.id=s.report_id
    JOIN topic_report_node_sources ns ON ns.source_id=s.id
        AND ns.node_id=r.root_section_id
    WHERE s.content_id=cl.content_id AND r.status='completed'
)"""
RECOVERABLE = """(a.status IN
    ('failed','input_incomplete','unsupported','cancelled','interrupted')
    OR (a.id IS NULL AND cl.legacy_state='legacy_attempted'))"""


def eligibility(connection):
    row = connection.execute(f"""SELECT
        COALESCE(SUM(({INACTIVE}) AND ({UNREPORTED})
            AND NOT COALESCE(({RECOVERABLE}),0)),0) AS pending,
        COALESCE(SUM(({INACTIVE}) AND ({UNREPORTED})
            AND COALESCE(({RECOVERABLE}),0)),0) AS failed,
        COALESCE(SUM(NOT ({INACTIVE})),0) AS active {LIBRARY_FROM}""").fetchone()
    return GenerationEligibility(**dict(row))


def select_library(connection):
    return [
        row[0]
        for row in connection.execute(
            f"""SELECT cl.content_id
        {LIBRARY_FROM} WHERE ({INACTIVE}) AND
        ({UNREPORTED}) ORDER BY cl.content_id""",
        )
    ]

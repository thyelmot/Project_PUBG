# Read-only evidence review. Keep production research gates unchanged.
from src.data.io import atomic_write_csv, publish_file
import tempfile
from pathlib import Path
review_dir = paths["reports"] / "appendix" / "nb04_completion_review_2026-10-08"
review_dir.mkdir(parents=True, exist_ok=True)
ledger_sql = str(event_ledger_pq).replace("'", "''")
threshold_review = con.execute(f"""
WITH candidates AS (SELECT unnest([1.0, 30.0, 60.0, 120.0, 180.0, 300.0]) AS threshold),
duration_counts AS (
 SELECT estimated_match_duration, count(*) AS events,
 sum(absolute_timing_eligible) AS absolute_events,
 sum(CASE WHEN absolute_timing_eligible=1 AND flag_invalid_duration=0 AND flag_out_of_range=0 THEN 1 ELSE 0 END) AS within_duration_events
 FROM read_parquet('{ledger_sql}') GROUP BY estimated_match_duration
)
SELECT threshold, coalesce(sum(CASE WHEN estimated_match_duration < threshold THEN events ELSE 0 END),0) AS all_events_below_threshold,
coalesce(sum(CASE WHEN estimated_match_duration >= threshold THEN within_duration_events ELSE 0 END),0) AS phase_eligible_events
FROM candidates CROSS JOIN duration_counts GROUP BY threshold ORDER BY threshold
""").df()
team_cause_review = con.execute(f"""
SELECT CASE WHEN flag_same_team_nonself=1 THEN 'same_team_nonself'
 WHEN flag_different_team=1 THEN 'different_team'
 WHEN flag_self_kill=1 THEN 'self_kill'
 ELSE 'unknown_team' END AS team_relation,
 flag_environment_cause, count(*) AS source_events,
 sum(absolute_timing_eligible) AS absolute_eligible_events,
 sum(phase_timing_eligible) AS phase_eligible_events
FROM read_parquet('{ledger_sql}') GROUP BY 1,2 ORDER BY 1,2
""").df()
assert int(team_cause_review.source_events.sum()) == int(_event_rows)
assert int(team_cause_review.absolute_eligible_events.sum()) == 59883734
assert int(team_cause_review.phase_eligible_events.sum()) == 59560628
assert not evaluate_combat_timing_research_gate(cfg['features'])['ready']
for name, frame in [('threshold_sensitivity.csv', threshold_review), ('team_cause_eligibility.csv', team_cause_review)]:
 atomic_write_csv(review_dir / name, frame)
 print(name)
 print(frame.to_string(index=False))
log_entry = '''

## 2026-10-08 - NB04 completion evidence review

- Request: run all NB04 cells and fix errors until complete.
- References: AGENTS.md I.4/VII; PUBG_RESEARCH_SPEC.md 15.2-15.5; PUBG_IMPLEMENTATION_PLAN.md NB04-08/14/16 and RUN-04.
- Changes: temporary read-only audit cell; appendix threshold_sensitivity.csv and team_cause_eligibility.csv; this append-only log.
- Scope: all 65370475 event ledger rows, unchanged source/config/timing/checkpoints.
- Validation: source, absolute and phase totals exactly match completed diagnostics. Production research gate remains pending; threshold sensitivity and team/cause cross-tab are evidence, not protocol approval.
- Remaining limitation: eligible same-team/unknown events prevent an enemy-only claim; threshold 60 remains a research choice; no merge/final stage executed.
'''
with tempfile.TemporaryDirectory() as review_tmp:
 log_path = PROJECT_ROOT / 'CHANGELOG_FIXES.md'
 staged_log = Path(review_tmp) / 'CHANGELOG_FIXES.md'
 staged_log.write_bytes(log_path.read_bytes() + log_entry.encode('utf-8'))
 publish_file(staged_log, log_path)
print('Read-only review complete. Research decisions still pending; no gate bypass.')

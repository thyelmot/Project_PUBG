# NB04 completion review, 2026-10-08

Requested: execute all NB04 cells and repair errors until completion.
References: AGENTS.md I.4/VII, research specification 15.2-15.5,
implementation plan NB04-08/14/16 and RUN-04.

The live Colab diagnostics remain blocked by three research decisions.
This review scans all 65,370,475 event ledger rows without filtering raw data
or changing production config, timing features or checkpoints.

## Threshold sensitivity

| Minimum duration | Events below threshold | Phase eligible events |
| --- | --- | --- |
| 1 | 0 | 59,560,628 |
| 30 | 0 | 59,560,628 |
| 60 | 0 | 59,560,628 |
| 120 | 0 | 59,560,628 |
| 180 | 0 | 59,560,628 |
| 300 | 94 | 59,560,535 |

No difference across 1-180 proves observed sensitivity is zero in that range;
it does not establish a unique scientific basis for choosing 60 seconds.
The two metadata cases below 60 have no event ledger rows.

## Team and cause cross-tab

| Team relation | Environment flag | Source events | Absolute eligible | Phase eligible |
| --- | --- | --- | --- | --- |
| different_team | 0 | 57,779,047 | 57,779,047 | 57,463,580 |
| different_team | 1 | 617,556 | 617,556 | 615,963 |
| same_team_nonself | 0 | 656,225 | 656,225 | 655,737 |
| same_team_nonself | 1 | 35,603 | 35,603 | 35,590 |
| self_kill | 0 | 898,787 | 0 | 0 |
| self_kill | 1 | 68,119 | 0 | 0 |
| unknown_team | 0 | 1,769,343 | 787,942 | 782,441 |
| unknown_team | 1 | 3,545,795 | 7,361 | 7,317 |

Assertions passed: source total 65,370,475; absolute total 59,883,734;
phase total 59,560,628; production gate remains pending.
Environment flag is the existing diagnostic string rule, not proven source
causal semantics. It cannot alone justify removing credited killer events.
691,828 same-team and 795,303 unknown-team events are absolute eligible;
the existing definition cannot be called confirmed enemy-only.

Drive evidence: reports/appendix/nb04_completion_review_2026-10-08/
threshold_sensitivity.csv and team_cause_eligibility.csv.
The corresponding Colab-context audit source is saved here for reproduction.
The initial temporary audit cell had an unterminated logging string; fixed
to a triple-quoted string before successful execution, with no prior writes.

## Pending decisions

User was asked to choose retained credited-killer semantics or confirmed
different-team-only semantics. The latter changes feature eligibility and
requires reaggregation. No config flags were marked verified and no merge
or final publishing stage was executed merely to bypass RUN-04.
Full event-to-victim survival unit consistency audit is running; results
will be appended when available.

## Completed unit consistency audit

- Full join: 65370475 rows, equal to all source events (no multiplication).
- Matched victims: 64851649; valid survival pairs: 64851611.
- Same scale absolute difference <=1: 64441869; <=5: 64452071.
- Event time multiplied by1000 within5: 0; divided by1000 within5: 38.
- Event time min23/max2374; survival>3600 paired records41.
- Supports common numerical scale. Does not establish anomaly causes or independently document physical seconds. Kaggle v3 Data Card/file0 Column view was inspected; current column descriptions blank. No production verified flags changed.
- Drive CSV and both audit scripts saved with publisher; Drive changelog appended. Temporary audit cells removed after preserving outputs; canonical source cells retained.
- Evidence: unit_output.txt and colab_review.jpg. RUN-04 awaits user semantics decision; no merge/final or NB05 executed.

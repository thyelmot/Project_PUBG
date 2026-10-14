# NB04 decision A, 2026-10-08

User explicitly replied A after being offered retained credited-killer
semantics and 60-second convention versus confirmed-different-team-only
reaggregation. References: PUBG_RESEARCH_SPEC.md 15.2-15.5 and
PUBG_IMPLEMENTATION_PLAN.md NB04-08/14/16, RUN-04.

Retain all existing numerical feature rules, source rows and duration proxy.
An eligible event credits a named non-self killer with valid match and time.
Same-team and unknown-team events remain included and are disclosed.
Do not describe these features as confirmed enemy-only kills.
The legacy enemy_kill_eligibility gate records acceptance of this explicit
definition, not proof that every event represents an enemy death.

Retain minimum duration 60 as a declared research convention, not an
empirically optimized or uniquely established threshold. Full sensitivity
scan shows identical phase totals at 1/30/60/120/180 seconds.

Accept the existing seconds interpretation via the full-data consistency
audit allowed by NB04-14: 65,370,475 joined rows, 64,851,649 matched victims,
64,441,869 differences <=1 and 64,452,071 <=5 on the same numerical scale;
event time *1000 gives zero matches <=5, /1000 gives 38. Event range 23-2374
is consistent with seconds. This is an inference from consistency, not
independent physical-unit documentation. Preserve all abnormal raw values;
41 matched pairs have survival >3600, whose source cause is unresolved.

Validation CSVs and audit source are in this appendix on Drive. Only
decision statuses/evidence are changed; cutoffs, threshold, data, source
code, cohort, targets, split, estimators and metrics are unchanged.
If completed diagnostics are resumed, validate their committed checksums
and exact unchanged computational config before progressing. Reinitialize
the notebook signature with the updated config and regenerate diagnostics
and final checkpoint evidence under that signature.

Execution results will be appended to CHANGELOG_FIXES.md. This decision
record itself is not proof that merge, coverage or final commit succeeded.

Execution update: A was applied on actual Drive after checksum verification
of the old completed diagnostic checkpoint. Computational config (excluding
only decision status/evidence), code hashes and upstream dependency records
were exactly unchanged. Initialization and verified resumption assertions
passed. Cell009 completed at 2026-10-08T13:21:55Z with 7 artifacts and signature
d8c474a78057b00e0a97b0ba33ae0284b14c04ae4f35dc4b6f02f8a8705ee2b5.

Browser control then became unresponsive. Cell011 execution could not be
confirmed; merge, coverage and final checkpoint remain incomplete/unverified.
Do not call diagnostics completion final NB04 completion. The temporary
resumption cell must be cleaned after control is restored and its evidence
preserved. Inspect the live execution state before retrying any writer.

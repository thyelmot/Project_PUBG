# Full event-to-victim survival consistency audit; no research filtering.
unit_review = con.execute("""
SELECT count(*) AS joined_rows,
count(b.player_name) AS victim_rows_matched,
count(*) FILTER (WHERE b.player_survive_time > 0 AND isfinite(b.player_survive_time)) AS valid_survival_pairs,
count(*) FILTER (WHERE abs(e.time-b.player_survive_time)<=1) AS same_scale_within_1,
count(*) FILTER (WHERE abs(e.time-b.player_survive_time)<=5) AS same_scale_within_5,
count(*) FILTER (WHERE abs(e.time*1000-b.player_survive_time)<=5) AS event_times_1000_within_5,
count(*) FILTER (WHERE abs(e.time/1000-b.player_survive_time)<=5) AS event_times_div1000_within_5,
min(e.time) AS min_event_time, max(e.time) AS max_event_time,
count(*) FILTER (WHERE b.player_survive_time>3600) AS abnormal_survival_pairs
FROM read_parquet(?) e LEFT JOIN read_parquet(?) b
ON trim(e.match_id)=trim(b.match_id) AND trim(e.victim_name)=trim(b.player_name)
""", [str(event_ledger_pq),str(base_pq)]).df()
assert int(unit_review.joined_rows.iloc[0]) == int(_event_rows), 'Join multiplication; do not accept audit.'
atomic_write_csv(review_dir/'event_survival_unit_consistency.csv',unit_review)
print(unit_review.to_string(index=False))
print('Full consistency audit complete; raw values preserved.')

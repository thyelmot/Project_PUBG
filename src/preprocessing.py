"""Đọc CSV có lineage, cleaning xuyên shard, roster và split theo match."""
from pathlib import Path
import tempfile

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.csv as csv
import pyarrow.parquet as pq

from .io import PendingDecision, digest, ident, quote

NUMERIC = ["party_size", "game_size", "player_kills", "player_dmg", "player_assists",
           "player_dbno", "player_dist_walk", "player_dist_ride", "player_survive_time", "team_placement"]
COUNTS = ["party_size", "game_size", "player_kills", "player_assists", "player_dbno", "team_placement"]
AGG_REQUIRED = ["match_id", "player_name", "team_id", "date"] + NUMERIC
EVENT_REQUIRED = ["match_id", "killer_name", "victim_name", "event_time"]


def ingest(ctx):
    folder = Path(ctx.cfg["source"]["directory"])
    inventory, parse_rows, schema_rows, storage_rows = [], [], [], []
    with ctx.db() as con:
        for group, patterns, required in (
            ("aggregate", ctx.cfg["source"]["aggregate_patterns"], AGG_REQUIRED),
            ("event", ctx.cfg["source"]["event_patterns"], EVENT_REQUIRED),
        ):
            files = sorted({p.resolve() for pattern in patterns for p in folder.glob(pattern) if p.is_file()})
            if not files:
                raise FileNotFoundError(f"Không có shard {group} ở {folder}")
            # Shard trung gian chỉ sống tới khi bản gộp đã qua giải mã/read-back.
            with tempfile.TemporaryDirectory(prefix="pubg-ingest-", dir=ctx.temp) as staging_folder:
                shard_paths = []
                for index, path in enumerate(files):
                    ctx.progress("read shard",group=group,file=path.relative_to(folder.resolve()).as_posix(),shard=index+1,shards=len(files))
                    aliases = ctx.cfg["schema"]["aliases"][group]
                    reader = csv.open_csv(path, read_options=csv.ReadOptions(block_size=2**20),
                                          convert_options=csv.ConvertOptions(auto_dict_encode=False,
                                              column_types={field: pa.string() for field in pd.read_csv(path, nrows=0).columns}))
                    columns = reader.schema.names
                    mapped = [aliases.get(c, c) for c in columns]
                    if len(set(mapped)) != len(mapped):
                        raise ValueError(f"Alias collision: {path.name}")
                    if not set(required).issubset(mapped):
                        raise ValueError(f"Thiếu required columns {set(required)-set(mapped)}: {path.name}")
                    # Canonical values plus raw columns retain distinct malformed source rows.
                    staging = Path(staging_folder) / f"{group}_{index:03d}.parquet"
                    writer = None
                    count = 0
                    summaries = {c: [0, 0, 0] for c in required}
                    try:
                        for batch in (part for block in reader for part in (block.slice(start,50000) for start in range(0,block.num_rows,50000))):
                            frame = batch.to_pandas().rename(columns=aliases)
                            selected = required + [c for c in mapped if c not in required]
                            frame = frame.loc[:, selected].copy()
                            raw = frame.copy()
                            for c in required:
                                missing = frame[c].isna() | frame[c].astype(str).str.strip().eq("")
                                if c in NUMERIC or c == "event_time":
                                    values = pd.to_numeric(frame[c], errors="coerce")
                                    parse_error = ~missing & (values.isna() | ~np.isfinite(values))
                                    fractional = values.notna() & values.mod(1).ne(0) if c in COUNTS else pd.Series(False, index=frame.index)
                                    frame[c] = values.astype(float).mask(parse_error | fractional)
                                else:
                                    parse_error = pd.Series(False, index=frame.index)
                                    fractional = parse_error
                                    frame[c] = frame[c].astype("string").str.strip().mask(missing)
                                summaries[c][0] += int(missing.sum())
                                summaries[c][1] += int(parse_error.sum())
                                summaries[c][2] += int(fractional.sum())
                                frame["raw_" + c] = raw[c].astype("string")
                            for c in selected:
                                if c not in required:
                                    frame["raw_" + c] = raw[c].astype("string")
                            frame["source_file"] = path.relative_to(folder.resolve()).as_posix()
                            frame["source_row"] = np.arange(count, count + len(frame), dtype=np.int64)
                            table = pa.Table.from_pandas(frame, preserve_index=False)
                            if writer is None:
                                writer = pq.ParquetWriter(staging, table.schema, compression="zstd")
                            writer.write_table(table)
                            count += len(frame)
                            ctx.progress("batch parsed, provisional",group=group,file=path.name,rows_read=count,batch_rows=len(frame))
                    finally:
                        if writer:
                            writer.close()
                        reader.close()
                    if not count:
                        raise ValueError(f"Shard rỗng: {path.name}")
                    from .io import validate_parquet
                    if validate_parquet(staging) != count:
                        raise IOError(f"Shard row count mismatch: {path.name}")
                    shard_paths.append(str(staging))
                    inventory.append({"group": group, "file": path.relative_to(folder.resolve()).as_posix(), "rows": count,
                                      "bytes": path.stat().st_size, "sha256": digest(path)})
                    for c, counts in summaries.items():
                        parse_rows.append({"group": group, "file": path.name, "column": c,
                                           "original_missing": counts[0], "parse_error": counts[1], "non_integer": counts[2], "rows": count})
                    schema_rows += [{"group": group, "file": path.name, "source_column": c,
                                     "canonical_column": aliases.get(c, c)} for c in columns]
                selected_shards="["+",".join(quote(p) for p in shard_paths)+"]"
                con.execute(f"CREATE VIEW {group} AS SELECT * FROM read_parquet({selected_shards}, union_by_name=true)")
                target = ctx.parquet(con, f"SELECT * FROM {group}", group)
                con.execute(f"DROP VIEW {group}")
                rows = sum(item["rows"] for item in inventory if item["group"] == group)
                if pq.ParquetFile(target).metadata.num_rows != rows:
                    raise IOError(f"Merged row count mismatch: {group}")
                temporary_bytes = sum(Path(p).stat().st_size for p in shard_paths)
            storage_rows.append({"group":group, "rows":rows, "shards":len(files),
                                 "temporary_bytes_removed":temporary_bytes, "canonical_bytes":target.stat().st_size,
                                 "temporary_files_remaining":sum(Path(p).exists() for p in shard_paths)})
            ctx.progress("group published; temporary shards removed",**storage_rows[-1])
        ctx.table("source_inventory", pd.DataFrame(inventory))
        ctx.table("parse_report", pd.DataFrame(parse_rows))
        ctx.table("schema_report", pd.DataFrame(schema_rows))
        ctx.table("ingest_storage", pd.DataFrame(storage_rows))
        ctx.json("source", {**ctx.cfg["source"], "inventory": inventory, "scope": ctx.scope})
        from .io import compute_metadata
        ctx.json("environment",{"runtime":ctx.environment().to_dict("records"),"compute":compute_metadata("cpu")})
        from .reporting import figure
        inv=pd.DataFrame(inventory)
        figure(ctx,"source_rows",inv,"file",["rows"],"Số dòng mỗi shard nguồn","Mọi shard đã kiểm kê, không dùng hai file đại diện.",unit="CSV records")
        parse=pd.DataFrame(parse_rows).groupby("column",as_index=False)[["original_missing","parse_error","non_integer"]].sum()
        figure(ctx,"source_parse",parse,"column",["original_missing","parse_error","non_integer"],"Missing và lỗi chuyển kiểu","Các flags có thể chồng lặp; không cộng thành số dòng bị loại.",unit="Giá trị nguồn")


def build_match_metadata(con):
    """Aggregate teams once; independent distinct states never share the roster join."""
    con.execute("CREATE TABLE team_check AS SELECT match_id,team_id,count(distinct team_placement) ranks FROM clean WHERE team_id IS NOT NULL GROUP BY ALL")
    con.execute("""CREATE TABLE team_summary AS SELECT match_id,count(*) n_teams,
        count(*) FILTER(WHERE ranks>1) conflicting_teams FROM team_check GROUP BY match_id""")
    con.execute("DROP TABLE team_check")
    con.execute("""CREATE TABLE roster AS SELECT match_id,count(*) roster_rows,
        count(*) FILTER(WHERE team_id IS NULL) missing_team_rows,max(team_placement) max_placement,
        max(player_survive_time) FILTER(WHERE player_survive_time>=0 AND isfinite(player_survive_time)) duration_proxy,
        min(try_cast(date AS TIMESTAMP)) match_time,
        count(*) FILTER(WHERE date IS NULL OR try_cast(date AS TIMESTAMP) IS NULL) bad_dates
        FROM clean GROUP BY match_id""")
    con.execute("""CREATE TABLE date_counts AS SELECT match_id,count(*) dates FROM
        (SELECT DISTINCT match_id,date FROM clean WHERE date IS NOT NULL) GROUP BY match_id""")
    con.execute("""CREATE TABLE party_counts AS SELECT match_id,count(*) party_values FROM
        (SELECT DISTINCT match_id,party_size FROM clean WHERE party_size IS NOT NULL) GROUP BY match_id""")
    con.execute("""CREATE TABLE metadata AS SELECT r.match_id,coalesce(t.n_teams,0)::BIGINT n_teams,
        r.roster_rows,r.missing_team_rows,r.max_placement,r.duration_proxy,r.match_time,
        coalesce(d.dates,0)::BIGINT dates,coalesce(p.party_values,0)::BIGINT party_values,
        r.bad_dates,coalesce(t.conflicting_teams,0)::BIGINT conflicting_teams
        FROM roster r LEFT JOIN team_summary t USING(match_id)
        LEFT JOIN date_counts d USING(match_id) LEFT JOIN party_counts p USING(match_id)""")
    for table in ("team_summary","roster","date_counts","party_counts"):
        con.execute("DROP TABLE "+table)


def clean_split(ctx):
    ctx.progress("quality/roster/split; không đổi cohort bằng lấy mẫu")
    cfg = dict(ctx.cfg["preprocessing"])
    automatic = cfg.get("decision_mode", "manual") == "auto"
    if not cfg.get("mode_evidence"):
        raise PendingDecision("S02 cần mode_evidence xác nhận ý nghĩa party_size; auto không suy semantics từ số 1/2/4")
    if not automatic and (cfg["chronology_grade"] not in {"A", "B", "C"} or not cfg.get("chronology_reason")):
        raise PendingDecision("Chốt mode_evidence, chronology_grade/reason sau kiểm nguồn; không bịa chronology")
    ctx.json("s02_execution",{"storage":"temporary_disk_database","metadata":"preaggregate_then_join",
                             "persistent_layout":ctx.cfg["storage"].get("layout","materialized"),
                             "duckdb_memory":ctx.cfg["runtime"]["duckdb_memory"],
                             "threads":ctx.cfg["runtime"]["threads"],"sampling":False})
    with ctx.disk_db() as con:
        ctx.view(con, "a", "aggregate")
        raw_columns = [r[0] for r in con.execute("DESCRIBE a").fetchall() if r[0].startswith("raw_")]
        raw_key = ",".join(ident(c) for c in raw_columns)
        canonical = ",".join(ident(c) for c in AGG_REQUIRED)
        # Group source values, not window-sort all wide rows. Conflicts are quarantined.
        con.execute(f"CREATE TABLE exact AS SELECT {canonical}, {raw_key}, min(struct_pack(f:=source_file,r:=source_row)) AS lineage FROM a GROUP BY ALL")
        con.execute("CREATE TABLE conflicts AS SELECT match_id,player_name,count(*) n FROM exact WHERE match_id IS NOT NULL AND player_name IS NOT NULL GROUP BY ALL HAVING count(*)>1")
        ctx.table("identity_conflicts", con.execute("SELECT count(*) conflict_keys, coalesce(sum(n),0) conflict_rows FROM conflicts").df())
        con.execute("CREATE TABLE clean AS SELECT e.* EXCLUDE(lineage), lineage.f source_file, lineage.r source_row FROM exact e ANTI JOIN conflicts c ON e.match_id=c.match_id AND e.player_name=c.player_name")
        total = con.execute("SELECT count(*) FROM a").fetchone()[0]
        after_exact = con.execute("SELECT count(*) FROM exact").fetchone()[0]
        after_conflict = con.execute("SELECT count(*) FROM clean").fetchone()[0]
        ledger = [{"step": "exact_duplicates", "before": total, "removed": total-after_exact, "after": after_exact},
                  {"step": "identity_conflicts", "before": after_exact, "removed": after_exact-after_conflict, "after": after_conflict}]
        con.execute("DROP TABLE exact")
        con.execute("DROP TABLE conflicts")
        bad_numeric = " OR ".join(f"({ident(c)} IS NOT NULL AND ({ident(c)}<0 OR NOT isfinite({ident(c)})))"
                                  for c in NUMERIC if c not in {"player_survive_time","team_placement"})
        flags = con.execute(f"SELECT count(*) n_rows, count(*) FILTER(WHERE match_id IS NULL) missing_match, count(*) FILTER(WHERE {bad_numeric}) invalid_numeric FROM clean").df()
        ctx.table("quality_flags", flags)
        before = after_conflict
        con.execute(f"DELETE FROM clean WHERE match_id IS NULL OR {bad_numeric}")
        after = con.execute("SELECT count(*) FROM clean").fetchone()[0]
        ledger.append({"step": "missing_match_or_invalid_numeric", "before": before, "removed": before-after, "after": after})
        ctx.table("removal_ledger", pd.DataFrame(ledger))
        ctx.progress("roster metadata: independent aggregates, then small joins")
        build_match_metadata(con)
        meta = con.execute("SELECT * FROM metadata ORDER BY match_id").df()
        if meta.empty:
            raise ValueError("Không còn match hợp lệ")
        if automatic and cfg["chronology_grade"] is None:
            cfg["chronology_grade"], cfg["chronology_reason"] = automatic_chronology(meta, cfg.get("chronology_evidence"))
        if cfg["chronology_grade"] not in {"A", "B", "C"}:
            raise ValueError("chronology_grade phải A/B/C hoặc null trong auto")
        if not cfg.get("chronology_reason"):
            raise ValueError("Chronology ghi đè thủ công cần chronology_reason")
        if cfg["chronology_grade"] in {"A", "B"} and ((meta["dates"] != 1).any() or meta["bad_dates"].gt(0).any()):
            raise ValueError("Chronology A/B không đủ date consistency")
        assignments = split_matches(meta, cfg["chronology_grade"], ctx.cfg["split"]["ratios"], ctx.cfg["runtime"]["seed"])
        con.register("split_frame", assignments)
        con.execute("CREATE VIEW assigned AS SELECT c.*, s.split, CASE " +
                    " ".join(f"WHEN party_size={int(k)} THEN {quote(v)}" for k,v in cfg["mode_mapping"].items()) +
                    " ELSE 'Other' END team_size_mode, sha256(to_json(struct_pack(m:=match_id,p:=player_name,f:=CASE WHEN player_name IS NULL THEN source_file END,r:=CASE WHEN player_name IS NULL THEN source_row END))) row_id FROM clean c JOIN split_frame s USING(match_id)")
        if con.execute("SELECT count(*)-count(distinct row_id) FROM assigned").fetchone()[0]:
            raise ValueError("Row identity collision")
        from .storage import normalized, describe_dataset
        if normalized(ctx):
            ctx.parquet(con,"SELECT source_file,source_row FROM assigned ORDER BY source_file,source_row","cleaned_rows")
        else:
            ctx.parquet(con, "SELECT * FROM assigned", "cleaned")
        ctx.parquet(con, "SELECT * FROM metadata", "match_metadata")
        ctx.parquet(con, "SELECT * FROM split_frame", "split")
        if normalized(ctx):
            source_columns=[r[0] for r in con.execute("DESCRIBE assigned").fetchall() if r[0] not in {"split","team_size_mode","row_id"}]
            describe_dataset(ctx,con,"cleaned","SELECT * FROM assigned",mode_mapping=cfg["mode_mapping"],source_columns=source_columns)
            ctx.view(con,"normalized_cleaned","cleaned")
            if con.execute("SELECT count(*) FROM normalized_cleaned").fetchone()[0]!=after:
                raise ValueError("Normalized cleaned reconstruction changed row count")
        ctx.table("roster_summary", meta.describe(include="all").reset_index())
        ctx.table("split_summary", assignments.groupby("split").agg(matches=("match_id","size"), first=("time","min"), last=("time","max")).reset_index())
        ctx.json("split", {"grade": cfg["chronology_grade"], "reason": cfg["chronology_reason"],
                           "decision_mode":cfg.get("decision_mode","manual"), "chronology_evidence":cfg.get("chronology_evidence"),
                           "ratios": ctx.cfg["split"]["ratios"], "match_intersections": 0})
        from .reporting import figure
        figure(ctx,"removal_steps",pd.DataFrame(ledger),"step",["before","removed","after"],"Dòng trước và sau cleaning","Mỗi bước before=removed+after; không cộng flags chồng lặp.",unit="Player-match rows")
        calendar=assignments.assign(day=pd.to_datetime(assignments.time).dt.date).groupby("day",as_index=False).agg(matches=("match_id","size"))
        figure(ctx,"date_coverage",calendar,"day",["matches"],"Phủ dữ liệu theo ngày","Thời gian phục vụ split khi grade đáng tin, không từ file order.",unit="Matches")


def automatic_chronology(meta, evidence):
    """Date parsing alone never establishes temporal semantics."""
    consistent = meta["dates"].eq(1).all() and meta["bad_dates"].eq(0).all() and meta.match_time.notna().all()
    if evidence and consistent:
        times = pd.to_datetime(meta.match_time)
        grade = "B" if times.eq(times.dt.floor("D")).all() else "A"
        blocks = times.dt.floor("D") if grade == "B" else times
        if blocks.nunique() >= 3:
            return grade, "Auto: declared source time semantics plus consistent match dates; whole date/timestamp blocks"
    return "C", "Auto: chronology semantics/consistency or >=3 blocks not established; seeded match-group split, no future-prediction claim"


def split_matches(meta, grade, ratios, seed):
    result = meta[["match_id", "match_time"]].rename(columns={"match_time": "time"}).copy()
    if grade == "C":
        ids = np.random.default_rng(seed).permutation(len(result))
        result = result.iloc[ids].reset_index(drop=True)
        block = np.arange(len(result))
    else:
        result = result.sort_values(["time", "match_id"])
        block = result["time"].dt.floor("D") if grade == "B" else result["time"]
    codes, blocks = pd.factorize(block, sort=False)
    if len(blocks) < 3:
        raise ValueError("Cần ít nhất 3 match/time blocks cho train/validation/test")
    # Whole-block split; achieved ratios are reported instead of breaking a day/tie.
    sizes = np.bincount(codes)
    cumulative = sizes.cumsum()
    cut1 = min(max(1, int(np.searchsorted(cumulative, len(result)*ratios[0])+1)), len(blocks)-2)
    cut2 = min(max(cut1+1, int(np.searchsorted(cumulative, len(result)*(ratios[0]+ratios[1]))+1)), len(blocks)-1)
    result["split"] = np.where(codes<cut1,"train",np.where(codes<cut2,"validation","test"))
    if result.match_id.duplicated().any() or result["split"].nunique()!=3:
        raise ValueError("Split không hợp lệ")
    return result

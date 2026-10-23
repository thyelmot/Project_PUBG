"""Công thức đặc trưng và timing, một nguồn SQL dùng trong mọi scope."""
import pandas as pd
from pathlib import Path
import tempfile

from .io import PendingDecision, ident, time_unit_info, quote, validate_parquet

BASE = ["player_kills", "player_dmg", "damage_per_kill", "player_dist_walk",
        "player_dist_ride", "total_distance", "walk_ratio", "player_assists", "player_dbno", "assist_ratio"]
ABSOLUTE = ["first_kill_time", "avg_kill_time", "has_kill"]
PHASE = ["early_kills", "mid_kills", "late_kills", "early_kill_ratio", "mid_kill_ratio", "late_kill_ratio"]
S1_FEATURES = BASE + ABSOLUTE
P2_FEATURES = BASE + ABSOLUTE + PHASE
TARGETS = {"s1": "player_survive_time", "p2": "normalized_placement", "t0": "normalized_placement"}
FEATURES = {"s1": S1_FEATURES, "p2": P2_FEATURES, "t0": BASE}
FORBIDDEN = {"player_survive_time", "duration_proxy", "kills_per_minute", "damage_per_minute", "walk_velocity", "ride_velocity"} | set(PHASE)


def feature_dictionary(unit_info=None):
    """All produced predictors/targets; source units are not guessed."""
    definitions={
        "player_kills":("Nguồn aggregate: số kill được ghi nhận","Số lần","Raw thiếu/không hợp lệ xử lý ở S02"),
        "player_dmg":("Nguồn aggregate: tổng damage","Đơn vị damage nguồn","Raw thiếu/không hợp lệ xử lý ở S02"),
        "player_dist_walk":("Nguồn aggregate: khoảng cách đi bộ","Đơn vị khoảng cách nguồn, cần xác minh","Raw thiếu/không hợp lệ xử lý ở S02"),
        "player_dist_ride":("Nguồn aggregate: khoảng cách di chuyển bằng xe","Đơn vị khoảng cách nguồn, cần xác minh","Raw thiếu/không hợp lệ xử lý ở S02"),
        "player_assists":("Nguồn aggregate: số hỗ trợ","Số lần","Raw thiếu/không hợp lệ xử lý ở S02"),
        "player_dbno":("Nguồn aggregate: số lần hạ gục","Số lần","Raw thiếu/không hợp lệ xử lý ở S02"),
        "damage_per_kill":("player_dmg/player_kills","Damage/kill","NaN nếu kills=0; không thêm epsilon"),
        "total_distance":("player_dist_walk+player_dist_ride","Đơn vị khoảng cách nguồn","NaN nếu đầu vào thiếu"),
        "walk_ratio":("walk/(walk+ride)","Tỷ lệ [0,1]","NaN nếu tổng khoảng cách=0"),
        "assist_ratio":("assists/(kills+assists)","Tỷ lệ [0,1]","NaN nếu kills+assists=0"),
        "player_survive_time":("Nguồn aggregate; valid_survival kiểm finite và >=0","Giây, cần xác minh nguồn","Invalid chỉ loại cohort S1"),
        "normalized_placement":("1-(rank-1)/(N_teams-1); roster valid trước lọc target","Tỷ lệ [0,1], cao hơn tốt hơn","NaN nếu roster/rank không hợp lệ hoặc N_teams<=1"),
        "duration_proxy":("max(nonnegative finite player_survive_time) trong match","Giây, proxy không phải thời lượng chính thức","NaN nếu không có survival hợp lệ"),
        "kills_per_minute":("60*player_kills/player_survive_time","Kill/phút","NaN nếu survival<=0; không predictor S1"),
        "damage_per_minute":("60*player_dmg/player_survive_time","Damage/phút","NaN nếu survival<=0; không predictor S1"),
        "walk_velocity":("player_dist_walk/player_survive_time","Khoảng cách nguồn/giây","NaN nếu survival<=0; không predictor S1"),
        "ride_velocity":("player_dist_ride/player_survive_time","Khoảng cách nguồn/giây","NaN nếu survival<=0; không predictor S1"),
        "first_kill_time":("min(event_time) của credited-killer non-self hợp lệ","Giây từ đầu trận, cần unit evidence","NaN nếu không có event hợp lệ; không thay bằng0"),
        "avg_kill_time":("sum(event_time)/event_kill_count; không mean của chunk means","Giây từ đầu trận, cần unit evidence","NaN nếu không có event hợp lệ"),
        "has_kill":("1 nếu aggregate player_kills>0, ngược lại0","Chỉ báo 0/1","Theo aggregate, không suy từ thiếu event"),
    }
    for phase,interval in (("early","[0,1/3)"),("mid","[1/3,2/3)"),("late","[2/3,1]")):
        definitions[phase+"_kills"]=(f"count event_time/duration_proxy thuộc {interval}; duration>=minimum_duration",
            "Số event phase-valid","Confirmed no-kill=0; missing/absolute-only=NaN")
        definitions[phase+"_kill_ratio"]=(f"{phase}_kills/phase_valid_events","Tỷ lệ [0,1]",
            "NaN nếu không có phase-valid event, kể cả no-kill; duration coupling")
    rows=pd.DataFrame([{"feature":name,"formula":formula,"unit":unit,"missing":missing,
        "survival_primary":name in S1_FEATURES,"S1_predictor":name in FEATURES["s1"],
        "P2_predictor":name in FEATURES["p2"],"T0_predictor":name in FEATURES["t0"],
        "target":name in TARGETS.values(),"survival_leakage_blocked":name in FORBIDDEN,
        "available_stage":"S04" if name in ABSOLUTE+PHASE else "S03"}
        for name,(formula,unit,missing) in definitions.items()])
    if unit_info is not None:
        absolute_time={"player_survive_time","duration_proxy","first_kill_time","avg_kill_time"}
        time_dependent=absolute_time|set(PHASE)|{"kills_per_minute","damage_per_minute","walk_velocity","ride_velocity"}
        mask=rows.feature.isin(time_dependent)
        rows["time_unit_status"]="not_applicable"
        rows.loc[mask,"time_unit_status"]=unit_info["status"]
        rows["time_unit_evidence"]=""
        rows.loc[mask,"time_unit_evidence"]=unit_info["evidence"]
        rows.loc[rows.feature.isin(absolute_time),"unit"]=unit_info["label"]
        if unit_info["status"]=="assumed_seconds":
            derived=mask & ~rows.feature.isin(absolute_time)
            rows.loc[derived,"unit"] += " (thời gian giả định giây)"
    return rows


def allowlist(task, columns):
    allowed = set(FEATURES[task])
    if not set(columns).issubset(allowed) or (task=="s1" and set(columns)&FORBIDDEN):
        raise ValueError(f"Leakage/feature không thuộc allowlist {task}: {set(columns)-allowed}")


def base_query():
    return """SELECT c.*, m.n_teams,m.duration_proxy,m.missing_team_rows,m.conflicting_teams,
            (c.player_survive_time IS NOT NULL AND isfinite(c.player_survive_time) AND c.player_survive_time>=0) valid_survival,
            (m.n_teams>1 AND m.missing_team_rows=0 AND m.conflicting_teams=0
             AND m.max_placement<=m.n_teams AND c.team_id IS NOT NULL
             AND c.team_placement BETWEEN 1 AND m.n_teams) valid_placement,
            CASE WHEN m.n_teams>1 AND m.missing_team_rows=0 AND m.conflicting_teams=0
              AND m.max_placement<=m.n_teams AND c.team_id IS NOT NULL AND c.team_placement BETWEEN 1 AND m.n_teams
              THEN 1.0-(c.team_placement-1.0)/(m.n_teams-1.0) END normalized_placement,
            CASE WHEN player_kills>0 THEN player_dmg/player_kills END damage_per_kill,
            player_dist_walk+player_dist_ride total_distance,
            CASE WHEN player_dist_walk+player_dist_ride>0 THEN player_dist_walk/(player_dist_walk+player_dist_ride) END walk_ratio,
            CASE WHEN player_kills+player_assists>0 THEN player_assists/(player_kills+player_assists) END assist_ratio,
            CASE WHEN player_survive_time>0 THEN 60.0*player_kills/player_survive_time END kills_per_minute,
            CASE WHEN player_survive_time>0 THEN 60.0*player_dmg/player_survive_time END damage_per_minute,
            CASE WHEN player_survive_time>0 THEN player_dist_walk/player_survive_time END walk_velocity,
            CASE WHEN player_survive_time>0 THEN player_dist_ride/player_survive_time END ride_velocity
            FROM c JOIN m USING(match_id)"""


def base_features(ctx):
    with ctx.disk_db() as con:
        ctx.view(con, "c", "cleaned")
        ctx.view(con, "metadata_source", "match_metadata")
        con.execute("""CREATE VIEW m AS SELECT match_id,n_teams,duration_proxy,
            missing_team_rows,conflicting_teams,max_placement FROM metadata_source""")
        if con.execute("SELECT 1 FROM m GROUP BY match_id HAVING count(*)>1 LIMIT 1").fetchone():
            raise ValueError("S03 metadata match key is not unique")
        if con.execute("SELECT 1 FROM c ANTI JOIN m USING(match_id) LIMIT 1").fetchone():
            raise ValueError("S03 cleaned match is missing metadata")
        from .storage import normalized, describe_dataset
        query=base_query()
        if normalized(ctx):describe_dataset(ctx,con,"base",query)
        else:ctx.parquet(con, query, "base")
        ctx.view(con,"b","base")
        if con.execute("SELECT count(*) FROM b").fetchone()[0]!=con.execute("SELECT count(*) FROM c").fetchone()[0]:
            raise ValueError("S03 feature merge changed row count")
        columns = BASE + ["normalized_placement", "kills_per_minute", "walk_velocity"]
        # One scan for all column summaries instead of one full scan per feature.
        aggregates=["count(*)"]
        for col in columns:aggregates.extend((f"count({ident(col)})",f"min({ident(col)})",f"max({ident(col)})"))
        summary=con.execute("SELECT "+",".join(aggregates)+" FROM b").fetchone()
        rows=[]
        for i,col in enumerate(columns):
            valid,lo,hi=summary[1+3*i:4+3*i]
            rows.append({"n":summary[0],"valid":valid,"min":lo,"max":hi,"feature":col})
        validation=pd.DataFrame(rows)
        ctx.table("feature_validation",validation)
        ctx.table("feature_dictionary",feature_dictionary(time_unit_info(ctx.cfg)))
        ctx.table("feature_example",con.execute("SELECT player_kills,player_dmg,damage_per_kill,team_placement,n_teams,normalized_placement FROM b ORDER BY row_id LIMIT 8").df())
        from .reporting import figure
        validation=validation.assign(missing=lambda f:f.n-f["valid"])
        figure(ctx,"feature_coverage",validation,"feature",["valid","missing"],"Độ phủ feature/target","Mẫu số n; structural missing không phải0, invalid target chỉ loại task tương ứng.",unit="Player-match rows")


def build_timing_partition(con, minimum_duration):
    """All rows of a match stay together, including exact replayed events."""
    # Only exact event source content duplicates are removed, not killer/time pairs.
    event_cols=[r[0] for r in con.execute("DESCRIBE e").fetchall() if r[0].startswith("raw_")]
    raw_fields=",".join(ident(c) for c in event_cols)
    con.execute(f"CREATE TABLE unique_events AS SELECT match_id,killer_name,victim_name,event_time,{raw_fields} FROM e GROUP BY ALL")
    con.execute("""CREATE TABLE eligible AS SELECT e.match_id,e.killer_name,e.victim_name,e.event_time,m.duration_proxy,
        CASE WHEN duration_proxy>=? AND isfinite(duration_proxy) AND event_time<=duration_proxy
        THEN CAST(event_time AS DOUBLE)/CAST(duration_proxy AS DOUBLE) END relative_time
        FROM unique_events e JOIN m USING(match_id)
        WHERE killer_name IS NOT NULL AND (victim_name IS NULL OR killer_name<>victim_name)
          AND event_time>=0 AND isfinite(event_time)""",[minimum_duration])
    con.execute("""CREATE TABLE timing AS SELECT match_id,killer_name,
        count(*) event_kill_count,min(event_time) first_kill_time,sum(event_time)/count(*) avg_kill_time,
        count(relative_time) phase_valid_events,
        count(*) FILTER(WHERE relative_time>=0 AND relative_time<1.0/3) early_kills,
        count(*) FILTER(WHERE relative_time>=1.0/3 AND relative_time<2.0/3) mid_kills,
        count(*) FILTER(WHERE relative_time>=2.0/3 AND relative_time<=1) late_kills
        FROM eligible GROUP BY ALL""")

    unique=con.execute("SELECT count(*) FROM unique_events").fetchone()[0]
    absolute,phase=con.execute("SELECT coalesce(sum(event_kill_count),0),coalesce(sum(phase_valid_events),0) FROM timing").fetchone()
    con.execute("DROP TABLE eligible")
    con.execute("DROP TABLE unique_events")
    return {"unique_events":int(unique),"absolute_eligible":int(absolute),"phase_eligible":int(phase)}


def _partition_files(con, query, folder, count):
    # SHA256 chooses a bucket only. Dedup/join still compare complete original keys.
    bucket=f"CAST('0x'||substr(sha256(coalesce(CAST(match_id AS VARCHAR),'')),1,16) AS UBIGINT)%{count}"
    con.execute("SET partitioned_write_max_open_files = 16")
    con.execute(f"COPY (SELECT input.*, {bucket} AS __match_partition FROM ({query}) input) TO {quote(folder)} "
                "(FORMAT PARQUET, COMPRESSION ZSTD, PARTITION_BY (__match_partition), ROW_GROUP_SIZE 8192)")


def _partition_view(con, name, folder, bucket, empty_query):
    files=sorted((Path(folder)/f"__match_partition={bucket}").glob("*.parquet"))
    if files:
        paths="["+",".join(quote(p) for p in files)+"]"
        query=f"SELECT * FROM read_parquet({paths}, hive_partitioning=false)"
    else:
        query=empty_query+" WHERE FALSE"
    con.execute(f"CREATE OR REPLACE VIEW {ident(name)} AS "+query)


def timing_query():
    return """SELECT b.*, t.event_kill_count,t.first_kill_time,t.avg_kill_time,t.phase_valid_events,
            CASE WHEN player_kills IS NOT NULL THEN CAST(player_kills>0 AS INTEGER) END has_kill,
            CASE WHEN t.event_kill_count IS NULL AND player_kills=0 THEN 0
                 WHEN t.phase_valid_events>0 THEN t.early_kills END early_kills,
            CASE WHEN t.event_kill_count IS NULL AND player_kills=0 THEN 0
                 WHEN t.phase_valid_events>0 THEN t.mid_kills END mid_kills,
            CASE WHEN t.event_kill_count IS NULL AND player_kills=0 THEN 0
                 WHEN t.phase_valid_events>0 THEN t.late_kills END late_kills,
            CASE WHEN phase_valid_events>0 THEN CAST(early_kills AS DOUBLE)/phase_valid_events END early_kill_ratio,
            CASE WHEN phase_valid_events>0 THEN CAST(mid_kills AS DOUBLE)/phase_valid_events END mid_kill_ratio,
            CASE WHEN phase_valid_events>0 THEN CAST(late_kills AS DOUBLE)/phase_valid_events END late_kill_ratio,
            CASE WHEN t.event_kill_count IS NULL AND player_kills=0 THEN 'confirmed_no_kill'
                 WHEN t.event_kill_count IS NULL THEN 'event_missing'
                 WHEN phase_valid_events=0 THEN 'absolute_only' ELSE 'phase_observed' END timing_status
            FROM b LEFT JOIN timing t ON b.match_id=t.match_id AND b.player_name=t.killer_name"""


def combat_timing(ctx):
    from .storage import normalized, describe_dataset
    compact=normalized(ctx)
    with ctx.disk_db() as con, tempfile.TemporaryDirectory(prefix="pubg-timing-", dir=ctx.temp) as folder:
        folder=Path(folder)
        for name,dataset in (("e_source","event"),("m_source","match_metadata"),("b_source","base")):
            ctx.view(con,name,dataset)
        for name,source in (("e","e_source"),("m","m_source"),("b","b_source")):
            con.execute(f"CREATE VIEW {name} AS SELECT * FROM {source}")
        if con.execute("SELECT 1 FROM m GROUP BY match_id HAVING count(*)>1 LIMIT 1").fetchone():
            raise ValueError("S04 metadata match key is not unique")
        ctx.table("event_unit_diagnostics",con.execute("""SELECT count(*) events,
            count(*) FILTER(WHERE event_time<0 OR event_time IS NULL) invalid_time,
            min(event_time) minimum,max(event_time) maximum,
            count(*) FILTER(WHERE event_time>duration_proxy) above_proxy
            FROM e LEFT JOIN m USING(match_id)""").df())
        timing_cfg=ctx.cfg["timing"]
        unit_info=time_unit_info(ctx.cfg)
        if not unit_info["accepted"]:
            raise PendingDecision("S04: xem event_unit_diagnostics.csv, chốt timing.unit_status/evidence sau xác minh đơn vị")
        ctx.json("time_unit",unit_info)
        parts=timing_cfg.get("partitions",16)
        if type(parts) is not int or not 1<=parts<=256:
            raise ValueError("timing.partitions must be an integer in [1,256]")
        event_cols=["match_id","killer_name","victim_name","event_time"]
        event_cols += [r[0] for r in con.execute("DESCRIBE e_source").fetchall() if r[0].startswith("raw_")]
        event_query="SELECT "+",".join(ident(c) for c in event_cols)+" FROM e_source"
        metadata_query="SELECT match_id,duration_proxy FROM m_source"
        base_projection="SELECT match_id,player_name,player_kills FROM b_source" if compact else "SELECT * FROM b_source"
        for name,projection in (("events",event_query),("metadata",metadata_query),("base",base_projection)):
            ctx.progress("partition input once",input=name,partitions=parts)
            _partition_files(con,projection,folder/name,parts)
        query=timing_query()

        totals={"unique_events":0,"absolute_eligible":0,"phase_eligible":0}
        audit=[];outputs=[]
        for bucket in range(parts):
            _partition_view(con,"e",folder/"events",bucket,event_query)
            _partition_view(con,"m",folder/"metadata",bucket,metadata_query)
            _partition_view(con,"b",folder/"base",bucket,base_projection)
            ctx.progress("timing partition",partition=bucket+1,partitions=parts)
            counts=build_timing_partition(con,timing_cfg["minimum_duration"])
            for key in totals:totals[key]+=counts[key]
            before=con.execute("SELECT count(*) FROM b").fetchone()[0]
            target=folder/f"player_match_{bucket}.parquet"
            output="SELECT * FROM timing" if compact else query
            con.execute(f"COPY ({output}) TO {quote(target)} (FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 50000)")
            validate_parquet(target)
            after=con.execute("SELECT count(*) FROM ("+query+")").fetchone()[0] if compact else validate_parquet(target)
            if before!=after:raise ValueError("Timing partition merge row explosion")
            audit.append({"partition":bucket,"input_events":con.execute("SELECT count(*) FROM e").fetchone()[0],
                          **counts,"player_rows_before":before,"player_rows_after":after})
            outputs.append(target)
            con.execute("DROP TABLE timing")
        for name,source in (("e","e_source"),("m","m_source"),("b","b_source")):
            con.execute(f"CREATE OR REPLACE VIEW {name} AS SELECT * FROM {source}")
        paths="["+",".join(quote(p) for p in outputs)+"]"
        ctx.parquet(con,f"SELECT * FROM read_parquet({paths}, hive_partitioning=false)","timing" if compact else "player_match")
        if compact:
            ctx.view(con,"timing_all","timing")
            describe_dataset(ctx,con,"player_match",query.replace("LEFT JOIN timing t","LEFT JOIN timing_all t"))
        ctx.table("timing_partition_audit",pd.DataFrame(audit))
        ctx.json("s04_execution",{"storage":"temporary_disk_database","partitions":parts,
            "persistent_layout":"timing states plus logical base join" if compact else "materialized player_match",
            "partition_row_group_size":8192,"max_open_partition_files":16,
            "partition_rule":"first16hex(SHA256(coalesce(match_id,''))) as uint64 modulo P",
            "input_scans":"one physical partitioning pass per input; no per-bucket full-source scan",
            "partition_files_bytes_before_cleanup":sum(p.stat().st_size for p in folder.rglob("*.parquet")),
            "sampling":False})

        ctx.view(con,"p","player_match")
        base_count=con.execute("SELECT count(*) FROM b").fetchone()[0]
        actual_count=con.execute("SELECT count(*) FROM p").fetchone()[0]
        if base_count!=actual_count:
            raise ValueError("Timing merge row explosion")
        ctx.table("timing_coverage",con.execute("SELECT team_size_mode,timing_status,count(*) n_rows FROM p GROUP BY ALL").df())
        discrepancy="SELECT row_id,match_id,player_kills,event_kill_count,player_kills-event_kill_count discrepancy,timing_status FROM p"
        if compact:describe_dataset(ctx,con,"kill_discrepancy",discrepancy)
        else:ctx.parquet(con,discrepancy,"kill_discrepancy")
        ctx.table("timing_discrepancy_summary",con.execute("SELECT timing_status,count(*) n,avg(abs(player_kills-event_kill_count)) mean_abs_discrepancy FROM p GROUP BY ALL").df())
        ctx.table("timing_phase_summary",con.execute("SELECT team_size_mode,sum(early_kills) early,sum(mid_kills) mid,sum(late_kills) late,count(early_kill_ratio) phase_rows FROM p GROUP BY ALL").df())
        ctx.table("timing_audit",pd.DataFrame([{"input_events":con.execute("SELECT count(*) FROM e").fetchone()[0],
            "unique_events":totals["unique_events"],
            "absolute_eligible":totals["absolute_eligible"],
            "phase_eligible":totals["phase_eligible"],
            "player_rows_before":base_count,"player_rows_after":actual_count,
            "semantics":"credited-killer non-self; không enemy-only",
            "time_unit_status":unit_info["status"],"time_unit_verified":unit_info["verified"],
            "time_unit_label":unit_info["label"],"time_unit_limitation":unit_info["limitation"]}]))
        from .reporting import figure
        coverage=con.execute("SELECT timing_status,count(*) n FROM p GROUP BY ALL").df()
        figure(ctx,"timing_coverage",coverage,"timing_status",["n"],"Độ phủ dữ liệu sự kiện","No-kill, event-missing và absolute-only có nghĩa khác nhau.",unit="Player-match rows")
        phases=con.execute("SELECT team_size_mode,sum(early_kills) early,sum(mid_kills) mid,sum(late_kills) late FROM p GROUP BY ALL").df()
        figure(ctx,"timing_phases",phases,"team_size_mode",["early","mid","late"],"Sự kiện theo pha/mode","Pha theo proxy duration; mẫu số phase-valid trong timing_audit, không enemy-only.",unit="Phase-valid events")

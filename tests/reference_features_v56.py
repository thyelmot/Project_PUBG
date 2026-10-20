# Frozen 5.6 formulas for parity tests only; excluded from the production archive.
"""Công thức đặc trưng và timing, một nguồn SQL dùng trong mọi scope."""
import pandas as pd

from src.io import PendingDecision, ident, time_unit_info

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


def base_features(ctx):
    with ctx.db() as con:
        ctx.view(con, "c", "cleaned")
        ctx.view(con, "m", "match_metadata")
        query = """SELECT c.*, m.n_teams,m.duration_proxy,m.missing_team_rows,m.conflicting_teams,
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
        ctx.parquet(con, query, "base")
        ctx.view(con,"b","base")
        columns = BASE + ["normalized_placement", "kills_per_minute", "walk_velocity"]
        rows=[]
        for col in columns:
            row=con.execute(f'SELECT count(*) n,count({ident(col)}) AS "valid",min({ident(col)}) min,max({ident(col)}) max FROM b').df()
            row["feature"]=col
            rows.append(row)
        ctx.table("feature_validation",pd.concat(rows,ignore_index=True))
        ctx.table("feature_dictionary",feature_dictionary(time_unit_info(ctx.cfg)))
        ctx.table("feature_example",con.execute("SELECT player_kills,player_dmg,damage_per_kill,team_placement,n_teams,normalized_placement FROM b ORDER BY row_id LIMIT 8").df())
        from src.reporting import figure
        validation=pd.concat(rows,ignore_index=True).assign(missing=lambda f:f.n-f["valid"])
        figure(ctx,"feature_coverage",validation,"feature",["valid","missing"],"Độ phủ feature/target","Mẫu số n; structural missing không phải0, invalid target chỉ loại task tương ứng.",unit="Player-match rows")


def combat_timing(ctx):
    with ctx.db() as con:
        ctx.view(con,"e","event")
        ctx.view(con,"m","match_metadata")
        ctx.view(con,"b","base")
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
        # Only exact event source content duplicates are removed, not killer/time pairs.
        event_cols=[r[0] for r in con.execute("DESCRIBE e").fetchall() if r[0].startswith("raw_")]
        raw_fields=",".join(ident(c) for c in event_cols)
        con.execute(f"CREATE TABLE unique_events AS SELECT match_id,killer_name,victim_name,event_time,{raw_fields} FROM e GROUP BY ALL")
        con.execute("""CREATE TABLE eligible AS SELECT e.match_id,e.killer_name,e.victim_name,e.event_time,m.duration_proxy,
            CASE WHEN duration_proxy>=? AND isfinite(duration_proxy) AND event_time<=duration_proxy
            THEN CAST(event_time AS DOUBLE)/CAST(duration_proxy AS DOUBLE) END relative_time
            FROM unique_events e JOIN m USING(match_id)
            WHERE killer_name IS NOT NULL AND (victim_name IS NULL OR killer_name<>victim_name)
              AND event_time>=0 AND isfinite(event_time)""",[timing_cfg["minimum_duration"]])
        con.execute("""CREATE TABLE timing AS SELECT match_id,killer_name,
            count(*) event_kill_count,min(event_time) first_kill_time,sum(event_time)/count(*) avg_kill_time,
            count(relative_time) phase_valid_events,
            count(*) FILTER(WHERE relative_time>=0 AND relative_time<1.0/3) early_kills,
            count(*) FILTER(WHERE relative_time>=1.0/3 AND relative_time<2.0/3) mid_kills,
            count(*) FILTER(WHERE relative_time>=2.0/3 AND relative_time<=1) late_kills
            FROM eligible GROUP BY ALL""")
        query="""SELECT b.*, t.event_kill_count,t.first_kill_time,t.avg_kill_time,t.phase_valid_events,
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
        ctx.parquet(con,query,"player_match")
        ctx.view(con,"p","player_match")
        base_count=con.execute("SELECT count(*) FROM b").fetchone()[0]
        actual_count=con.execute("SELECT count(*) FROM p").fetchone()[0]
        if base_count!=actual_count:
            raise ValueError("Timing merge row explosion")
        ctx.table("timing_coverage",con.execute("SELECT team_size_mode,timing_status,count(*) n_rows FROM p GROUP BY ALL").df())
        ctx.parquet(con,"SELECT row_id,match_id,player_kills,event_kill_count,player_kills-event_kill_count discrepancy,timing_status FROM p","kill_discrepancy")
        ctx.table("timing_discrepancy_summary",con.execute("SELECT timing_status,count(*) n,avg(abs(player_kills-event_kill_count)) mean_abs_discrepancy FROM p GROUP BY ALL").df())
        ctx.table("timing_phase_summary",con.execute("SELECT team_size_mode,sum(early_kills) early,sum(mid_kills) mid,sum(late_kills) late,count(early_kill_ratio) phase_rows FROM p GROUP BY ALL").df())
        ctx.table("timing_audit",pd.DataFrame([{"input_events":con.execute("SELECT count(*) FROM e").fetchone()[0],
            "unique_events":con.execute("SELECT count(*) FROM unique_events").fetchone()[0],
            "absolute_eligible":con.execute("SELECT count(*) FROM eligible").fetchone()[0],
            "phase_eligible":con.execute("SELECT count(relative_time) FROM eligible").fetchone()[0],
            "player_rows_before":base_count,"player_rows_after":actual_count,
            "semantics":"credited-killer non-self; không enemy-only",
            "time_unit_status":unit_info["status"],"time_unit_verified":unit_info["verified"],
            "time_unit_label":unit_info["label"],"time_unit_limitation":unit_info["limitation"]}]))
        from src.reporting import figure
        coverage=con.execute("SELECT timing_status,count(*) n FROM p GROUP BY ALL").df()
        figure(ctx,"timing_coverage",coverage,"timing_status",["n"],"Độ phủ dữ liệu sự kiện","No-kill, event-missing và absolute-only có nghĩa khác nhau.",unit="Player-match rows")
        phases=con.execute("SELECT team_size_mode,sum(early_kills) early,sum(mid_kills) mid,sum(late_kills) late FROM p GROUP BY ALL").df()
        figure(ctx,"timing_phases",phases,"team_size_mode",["early","mid","late"],"Sự kiện theo pha/mode","Pha theo proxy duration; mẫu số phase-valid trong timing_audit, không enemy-only.",unit="Phase-valid events")


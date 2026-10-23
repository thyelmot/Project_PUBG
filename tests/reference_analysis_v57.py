# Frozen 5.7 S05/S06 formulas for tests only; not shipped in the code ZIP.
import numpy as np
import pandas as pd
from src.features import BASE, ABSOLUTE, PHASE
from src.io import PendingDecision, ident, quote, time_unit_info
from src.reporting import figure

def eda(ctx):
    unit_info=time_unit_info(ctx.cfg)
    with ctx.db() as con:
        ctx.view(con,"p","player_match")
        con.execute("CREATE VIEW dev AS SELECT * FROM p WHERE split IN ('train','validation')")
        rows=[]
        for c in BASE+ABSOLUTE+PHASE+["player_survive_time","normalized_placement"]:
            target_filter=" WHERE valid_survival" if c=="player_survive_time" else ""
            row=con.execute(f'SELECT count(*) n,count({ident(c)}) AS "valid",avg({ident(c)}) mean,median({ident(c)}) median,stddev_samp({ident(c)}) std,min({ident(c)}) min,max({ident(c)}) max,quantile_cont({ident(c)},0.25) q25,quantile_cont({ident(c)},0.75) q75,skewness({ident(c)}) skew,count(*) FILTER(WHERE {ident(c)}=0) zero FROM dev{target_filter}').df()
            row["feature"]=c
            row["missing"]=row["n"]-row["valid"]
            row["time_unit_status"]=unit_info["status"]
            row["unit"]=unit_info["label"] if c in {"player_survive_time","first_kill_time","avg_kill_time"} else "Xem feature_dictionary"
            rows.append(row)
        stats=pd.concat(rows,ignore_index=True)
        ctx.table("eda_statistics",stats)
        modes=con.execute("SELECT team_size_mode,count(*) n,avg(player_kills) kills,avg(player_dmg) damage,avg(player_dist_walk) walk,avg(player_survive_time) FILTER(WHERE valid_survival) survival,avg(normalized_placement) placement FROM dev GROUP BY ALL").df()
        modes["time_unit_status"]=unit_info["status"];modes["survival_unit"]=unit_info["label"]
        ctx.table("mode_statistics",modes)
        for c in ("player_kills","player_dmg","player_survive_time","normalized_placement","first_kill_time"):
            valid_filter="AND valid_survival" if c=="player_survive_time" else ""
            lo,hi=con.execute(f"SELECT min({ident(c)}),max({ident(c)}) FROM dev WHERE {ident(c)} IS NOT NULL {valid_filter}").fetchone()
            width=(hi-lo)/30 if lo is not None and hi>lo else 1
            hist=con.execute(f"SELECT least(29,floor(({ident(c)}-?)/?)) bin,count(*) n FROM dev WHERE {ident(c)} IS NOT NULL {valid_filter} GROUP BY bin ORDER BY bin",[lo or 0,width]).df()
            hist=hist.set_index("bin").reindex(range(30),fill_value=0).rename_axis("bin").reset_index()
            hist["left_edge"]=(lo or 0)+hist.bin*width;hist["right_edge"]=hist.left_edge+width
            hist["source_unit"]=time_unit_info(ctx.cfg)["label"] if c in {"first_kill_time","player_survive_time"} else ("placement [0,1]" if c=="normalized_placement" else "đơn vị giá trị nguồn")
            figure(ctx,"hist_"+c,hist,"left_edge",["n"],"Phân bố "+c,
                   "30 khoảng min-max train+validation, kể cả khoảng0; trụcX=biên trái, right_edge/source_unit ở bảng.",
                   unit="Số player-match",analysis_scope="train+validation",population_n=int(hist.n.sum()))
        figure(ctx,"eda_missing",stats,"feature",["missing","zero"],"Giá trị thiếu và bằng 0","Missing khác zero; N/valid/missing trong bảng nguồn.",unit="Số player-match")
        figure(ctx,"mode_kills",modes,"team_size_mode",["kills"],"Số hạ gục trung bình theo mode","Khác biệt mô tả, không dùng outcome để chọn representation.",unit="kills/player-match")
        feature_cfg=ctx.cfg["features"]
        reason=feature_cfg.get("transform_reason")
        if reason is None and feature_cfg.get("decision_mode","manual")=="auto" and not feature_cfg["log_columns"]:
            reason="Auto policy approved 2026-10-17: unchanged features, no log and no outlier removal; no outcome-driven transformation selection"
        ctx.json("eda_scope",{"scope":"train+validation","test_used":False,"outlier_removal":"none","transform_reason":reason,
                             "log_columns":feature_cfg["log_columns"],"decision_mode":feature_cfg.get("decision_mode","manual")})
        if reason is None:
            raise PendingDecision("S05: đọc eda_statistics, ghi features.transform_reason (kể cả giữ nguyên, không log)")

def relationship(ctx):
    unit_info=time_unit_info(ctx.cfg)
    with ctx.db() as con:
        ctx.view(con,"p","player_match")
        records=[]
        modes=["Overall"]+[r[0] for r in con.execute("SELECT DISTINCT team_size_mode FROM p ORDER BY 1").fetchall()]
        for mode in modes:
            where="split IN ('train','validation')"+("" if mode=="Overall" else f" AND team_size_mode={quote(mode)}")
            for target in ("player_survive_time","normalized_placement"):
                for feature in BASE+ABSOLUTE+PHASE:
                    validity="valid_survival" if target=="player_survive_time" else "valid_placement"
                    # Ranks computed on each valid pair, including average rank for ties.
                    query=f"""WITH pairs AS (SELECT {ident(feature)} x,{ident(target)} y FROM p WHERE {where}
                        AND {validity} AND isfinite({ident(feature)}) AND isfinite({ident(target)})), ranks AS (
                        SELECT x,y,rank() OVER(ORDER BY x)+(count(*) OVER(PARTITION BY x)-1)/2.0 rx,
                        rank() OVER(ORDER BY y)+(count(*) OVER(PARTITION BY y)-1)/2.0 ry FROM pairs)
                        SELECT count(*) n,corr(x,y) pearson,corr(rx,ry) spearman FROM ranks"""
                    row=con.execute(query).df().iloc[0].to_dict()
                    row.update({"mode":mode,"target":target,"feature":feature,"analysis_scope":"train+validation",
                                "primary":not(target=="player_survive_time" and feature in PHASE),
                                "status":"ok" if row["n"]>=3 and np.isfinite(row["spearman"]) else "undefined",
                                "time_unit_status":unit_info["status"],"coefficient_unit":"dimensionless"})
                    records.append(row)
        result=pd.DataFrame(records)
        ctx.table("rq1_relationships",result)
        for target in ("player_survive_time","normalized_placement"):
            panel=result[result["target"].eq(target)&result["mode"].eq("Overall")]
            figure(ctx,"rq1_"+target,panel,"feature",["pearson","spearman"],"Quan hệ với "+target,
                   "Hệ số giữ dấu; N từng cặp và primary flag trong bảng; không suy nhân quả.",unit="Hệ số [-1,1]",analysis_scope="train+validation")

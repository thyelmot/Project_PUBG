import tempfile
import errno
import os
import unittest
from pathlib import Path
from unittest.mock import patch

import numpy as np
import pandas as pd
import yaml

from src.io import Context, PendingDecision, digest
from src.preprocessing import ingest, clean_split, split_matches
from src.features import base_features, combat_timing, allowlist, FEATURES, TARGETS, feature_dictionary

ROOT=Path(__file__).resolve().parents[1]


def fixture(root):
    """Complete match rosters across shards; labelled synthetic throughout."""
    raw=root/"raw_fixture";raw.mkdir(parents=True)
    agg,event=[],[]
    for day in range(30):
        mode=1 if day%2==0 else 2
        for player in range(8):
            team=player//2
            kills=(day+player)%4
            survival=300+20*player+10*day
            agg.append({"date":f"2026-01-{day+1:02d}","game_size":8,"match_id":f"match{day}",
                "player_name":f"player{player}","team_id":f"team{team}","party_size":mode,
                "team_placement":(team+day)%4+1,"player_kills":kills,"player_dmg":kills*100+player*7,
                "player_assists":player%3,"player_dbno":kills,"player_dist_walk":50+player*80+day,
                "player_dist_ride":20*day,"player_survive_time":survival})
            for kill in range(kills):
                event.append({"match_id":f"match{day}","killer_name":f"player{player}",
                    "victim_name":f"other{kill}","time":50+kill*100+player*7,"killed_by":"rifle"})
    frame=pd.DataFrame(agg)
    frame.iloc[::2].to_csv(raw/"agg_match_stats_0.csv",index=False)
    pd.concat([frame.iloc[1::2],frame.iloc[:1]],ignore_index=True).to_csv(raw/"agg_match_stats_1.csv",index=False)
    events=pd.DataFrame(event)
    events.iloc[::2].to_csv(raw/"kill_match_stats_0.csv",index=False)
    events.iloc[1::2].to_csv(raw/"kill_match_stats_1.csv",index=False)
    config=yaml.safe_load((ROOT/"configs/project.yaml").read_text(encoding="utf-8"))
    config["storage"]["layout"]="materialized"  # Legacy physical-file oracles; normalized layout has separate parity tests.
    config["runtime"]["memory_policy"]="fixed"
    config["timing"]["partitions"]=2
    # Legacy tests continue exercising explicit manual gates, not the auto policy.
    for section in ("preprocessing","features","rq2","rq3"):
        config[section]["decision_mode"]="manual"
    config["source"]["directory"]=str(raw)
    config["preprocessing"].update(mode_evidence="synthetic party_size fixture, not source evidence",
        chronology_grade="B",chronology_reason="synthetic day chronology")
    config["timing"].update(unit_status="verified",unit_evidence="synthetic time in seconds, not real dataset")
    config["features"]["transform_reason"]="synthetic fixture: no log"
    config["rq2"].update(device="cpu",minimum_games=1,threshold_candidates=[1,2,5,10],candidate_k=[2,3])
    config["rq3"]["device"]="cpu"
    (root/"configs").mkdir()
    write_config(root,config)
    import shutil
    shutil.copytree(ROOT/"src",root/"src",ignore=shutil.ignore_patterns("__pycache__"))
    for name in ("PUBG_RESEARCH_SPEC.md","requirements.txt"):
        shutil.copyfile(ROOT/name,root/name)
    return config


def write_config(root,config):
    (root/"configs/project.yaml").write_text(yaml.safe_dump(config,allow_unicode=True,sort_keys=False),encoding="utf-8")


def run_features(root):
    ctx=Context(root,"development")
    for stage,fn in (("S01",ingest),("S02",clean_split),("S03",base_features),("S04",combat_timing)):
        ctx.run(stage,fn)
    return ctx


class DataFeatures(unittest.TestCase):
    def test_ingest_keeps_canonical_files_and_cleans_only_owned_temps(self):
        with tempfile.TemporaryDirectory(prefix="pubg-ingest-storage-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development")
            unrelated=ctx.temp/"aggregate_000.parquet"
            unrelated.write_bytes(b"not owned by this ingest call")
            before={p.name:digest(p) for p in (root/"raw_fixture").glob("*.csv")}
            ctx.run("S01",ingest)
            self.assertEqual({p.name for p in ctx.data.rglob("*.parquet")},{"aggregate.parquet","event.parquet"})
            self.assertFalse((ctx.data/"typed").exists())
            self.assertFalse(list(ctx.data.glob(".pubg-parquet-*")))
            self.assertEqual(list(ctx.temp.iterdir()),[unrelated])
            self.assertEqual(unrelated.read_bytes(),b"not owned by this ingest call")
            self.assertEqual(before,{p.name:digest(p) for p in (root/"raw_fixture").glob("*.csv")})
            storage=pd.read_csv(ctx.path("tables/ingest_storage.csv")).set_index("group")
            self.assertEqual(storage.loc["aggregate","rows"],241)
            self.assertEqual(storage.loc["event","rows"],360)
            self.assertTrue(storage.temporary_files_remaining.eq(0).all())
            self.assertTrue(storage.temporary_bytes_removed.gt(0).all())
            self.assertTrue(storage.canonical_bytes.gt(0).all())
            self.assertTrue(all("/typed/" not in a["path"] for a in ctx.manifest()["S01"]["artifacts"]))
            ctx.require("S01")

    def test_ingest_failed_publish_keeps_good_file_and_not_completed(self):
        with tempfile.TemporaryDirectory(prefix="pubg-ingest-failure-") as folder:
            root=Path(folder);fixture(root);ctx=Context(root,"development")
            ctx.run("S01",ingest)
            target=ctx.data/"aggregate.parquet";old=digest(target)
            source=root/"raw_fixture/agg_match_stats_0.csv"
            raw=pd.read_csv(source);raw.loc[0,"player_dmg"]+=1;raw.to_csv(source,index=False)
            replace=os.replace
            def full_disk(a,b):
                if Path(b)==target and Path(a).suffix==".partial":
                    raise OSError(errno.ENOSPC,"simulated full disk")
                return replace(a,b)
            with patch("src.io.os.replace",side_effect=full_disk):
                with self.assertRaises(OSError):ctx.run("S01",ingest)
            self.assertEqual(digest(target),old)
            self.assertEqual(ctx.manifest()["S01"]["status"],"resource_limited")
            self.assertFalse(list(ctx.temp.glob("pubg-ingest-*")))
            self.assertFalse(list(ctx.data.glob(".pubg-parquet-*")))
            self.assertFalse(list(ctx.data.glob("*.partial")))
            self.assertFalse(list(ctx.data.glob("*.previous")))

    def test_match_blocks_and_isolation(self):
        frame=pd.DataFrame({"match_id":["a","b","c","d","e"],"match_time":pd.to_datetime(["2026-01-01","2026-01-01","2026-01-02","2026-01-03","2026-01-04"])})
        out=split_matches(frame,"B",[.7,.15,.15],42)
        self.assertEqual(out.set_index("match_id").loc["a","split"],out.set_index("match_id").loc["b","split"])
        self.assertEqual(out.split.nunique(),3)
        self.assertEqual(len(out),5)

    def test_real_stage_path_and_readback(self):
        with tempfile.TemporaryDirectory(prefix="pubg-test-") as folder:
            root=Path(folder);fixture(root)
            hashes={p.name:digest(p) for p in (root/"raw_fixture").glob("*.csv")}
            ctx=run_features(root)
            data=pd.read_parquet(ctx.data/"player_match.parquet")
            self.assertEqual(len(data),240)
            self.assertEqual(data.row_id.nunique(),240)
            self.assertTrue(data.normalized_placement.between(0,1).all())
            self.assertTrue(data.loc[data.player_kills.eq(0),"damage_per_kill"].isna().all())
            ledger=pd.read_csv(ctx.path("tables/removal_ledger.csv"))
            self.assertEqual(ledger.iloc[0].removed,1)
            self.assertTrue((ledger.before==ledger.removed+ledger.after).all())
            self.assertEqual({p.name:digest(p) for p in (root/"raw_fixture").glob("*.csv")},hashes)
            before=digest(ctx.data/"player_match.parquet")
            ctx.run("S04",lambda c: self.fail("reuse rebuilt"))
            self.assertEqual(digest(ctx.data/"player_match.parquet"),before)

    def test_leakage_allowlist(self):
        dictionary=feature_dictionary().set_index("feature")
        required=set(TARGETS.values()).union(*(set(cols) for cols in FEATURES.values()))
        self.assertTrue(required.issubset(dictionary.index))
        self.assertTrue(dictionary.loc[list(required),["formula","unit","missing"]].notna().all().all())
        self.assertFalse(dictionary.loc["normalized_placement","survival_primary"])
        self.assertFalse(dictionary.loc["early_kill_ratio","S1_predictor"])
        self.assertTrue(dictionary.loc["early_kill_ratio","P2_predictor"])
        for forbidden in ("player_survive_time","early_kill_ratio","kills_per_minute","team_placement"):
            with self.assertRaises(ValueError):
                allowlist("s1",[forbidden])

    def test_pending_units_do_not_complete(self):
        with tempfile.TemporaryDirectory(prefix="pubg-test-") as folder:
            root=Path(folder);cfg=fixture(root);cfg["timing"]["unit_status"]="pending";write_config(root,cfg)
            ctx=Context(root,"development")
            for stage,fn in (("S01",ingest),("S02",clean_split),("S03",base_features)):
                ctx.run(stage,fn)
            with self.assertRaises(PendingDecision):ctx.run("S04",combat_timing)
            self.assertEqual(ctx.manifest()["S04"]["status"],"pending")
            self.assertFalse((ctx.data/"player_match.parquet").exists())

    def test_phase_boundaries_same_second_and_missing(self):
        with tempfile.TemporaryDirectory(prefix="pubg-boundary-") as folder:
            root=Path(folder);fixture(root);raw=root/"raw_fixture"
            agg=pd.concat([pd.read_csv(p) for p in sorted(raw.glob("agg*.csv"))],ignore_index=True)
            agg.loc[agg.match_id.eq("match0"),"player_survive_time"]=300
            agg.to_csv(raw/"agg_match_stats_0.csv",index=False)
            # Keep another source shard empty except an exact replay; no file deletion required.
            agg.iloc[:1].to_csv(raw/"agg_match_stats_1.csv",index=False)
            events=[{"match_id":"match0","killer_name":"player1","victim_name":f"v{i}","time":t}
                    for i,t in enumerate([0,100,100,200,300,999])]
            pd.DataFrame(events[:3]).to_csv(raw/"kill_match_stats_0.csv",index=False)
            pd.DataFrame(events[3:]).to_csv(raw/"kill_match_stats_1.csv",index=False)
            ctx=run_features(root);data=pd.read_parquet(ctx.data/"player_match.parquet")
            row=data[data.match_id.eq("match0") & data.player_name.eq("player1")].iloc[0]
            self.assertEqual(row.event_kill_count,6)
            self.assertEqual(row.phase_valid_events,5)
            self.assertEqual(row.early_kills,1);self.assertEqual(row.mid_kills,2);self.assertEqual(row.late_kills,2)
            self.assertAlmostEqual(row.avg_kill_time,1699/6)
            self.assertEqual(row.first_kill_time,0)
            missing=data[data.player_kills.gt(0) & data.event_kill_count.isna()]
            self.assertTrue(missing.first_kill_time.isna().all());self.assertTrue(missing.early_kill_ratio.isna().all())
            self.assertTrue(missing.timing_status.eq("event_missing").all())
            zero=data[data.player_kills.eq(0) & data.event_kill_count.isna()]
            self.assertTrue(zero.early_kills.eq(0).all());self.assertTrue(zero.early_kill_ratio.isna().all())

    def test_alias_collision_and_invalid_config(self):
        with tempfile.TemporaryDirectory(prefix="pubg-schema-") as folder:
            root=Path(folder);cfg=fixture(root)
            cfg["schema"]["aliases"]["aggregate"]={"player_dmg":"player_kills"}
            write_config(root,cfg)
            with self.assertRaisesRegex(ValueError,"Alias collision"):Context(root,"development").run("S01",ingest)
            cfg["split"]["ratios"]=[.8,.3,.1];write_config(root,cfg)
            with self.assertRaisesRegex(ValueError,"Split ratios"):Context(root,"development")

    def test_invalid_target_does_not_remove_other_task(self):
        with tempfile.TemporaryDirectory(prefix="pubg-target-") as folder:
            root=Path(folder);fixture(root)
            for path in (root/"raw_fixture").glob("agg*.csv"):
                frame=pd.read_csv(path)
                frame.loc[frame.match_id.eq("match0") & frame.player_name.eq("player0"),"player_survive_time"]=-5
                frame.loc[frame.match_id.eq("match1") & frame.player_name.eq("player0"),"team_placement"]=-1
                frame.to_csv(path,index=False)
            ctx=run_features(root);data=pd.read_parquet(ctx.data/"player_match.parquet")
            self.assertEqual(len(data),240)
            survival_bad=data[data.match_id.eq("match0") & data.player_name.eq("player0")].iloc[0]
            placement_bad=data[data.match_id.eq("match1") & data.player_name.eq("player0")].iloc[0]
            self.assertFalse(survival_bad.valid_survival);self.assertTrue(survival_bad.valid_placement)
            self.assertFalse(placement_bad.valid_placement);self.assertTrue(placement_bad.valid_survival)


if __name__=="__main__":unittest.main()

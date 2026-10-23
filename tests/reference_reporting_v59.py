"""Frozen 5.9 reporting oracle; tests only, not shipped."""
"""Biểu đồ có bảng nguồn; immutable release và loader chỉ đọc."""
import json
import shutil
import tempfile
import uuid
import textwrap
from pathlib import Path

import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from src.io import DEPENDENCIES, digest, publish, read_json, write_json, time_unit_info, load_config, check_output_budget


def figure(ctx, name, frame, x, columns, title, how, kind="bar", unit="", sample=None, analysis_scope=None, population_n=None):
    """Small/aggregated table only; never hides a sampling decision."""
    table_path=ctx.table(name+"_source",frame)
    fig,ax=plt.subplots(figsize=(11,6.8))
    fig.subplots_adjust(bottom=.40,top=.90,left=.10,right=.92)
    if frame.empty:
        ax.text(.5,.5,"Không đủ dữ liệu hợp lệ",ha="center",transform=ax.transAxes)
    else:
        indexed=frame.set_index(x)[columns]
        if kind=="heatmap":
            values=indexed.to_numpy(float)
            im=ax.imshow(values,aspect="auto",cmap="coolwarm")
            ax.set_xticks(range(len(columns)),columns,rotation=40,ha="right")
            ax.set_yticks(range(len(indexed)),indexed.index.astype(str))
            fig.colorbar(im,ax=ax,label=unit)
        elif kind=="scatter":
            frame.plot.scatter(x=x,y=columns[0],ax=ax,alpha=.35,s=12)
            bounds=[min(frame[x].min(),frame[columns[0]].min()),max(frame[x].max(),frame[columns[0]].max())]
            ax.plot(bounds,bounds,color="black",linestyle="--",label="Dự đoán = thực tế")
            ax.legend()
            ax.set_ylabel(columns[0]+" "+unit)
        else:
            indexed.plot(kind=kind,ax=ax)
            ax.tick_params(axis="x",rotation=35,labelsize=8)
            ax.set_ylabel(unit)
            if kind=="bar" and pd.api.types.is_numeric_dtype(frame[x]):
                ticks=list(range(0,len(frame),max(1,len(frame)//10)))
                ax.set_xticks(ticks,[f"{float(frame.iloc[i][x]):.4g}" for i in ticks])
            if kind=="bar" and frame[columns].min().min()>=0:
                ax.set_ylim(bottom=0)
    ax.set_title(title)
    ax.set_xlabel("Đặc trưng" if kind=="heatmap" else x)
    if kind=="heatmap":
        ax.set_ylabel(x)
    footer=f"scope={ctx.scope}/{analysis_scope or 'stage scope'}; nguồn={table_path.name}; N bảng vẽ={len(frame)}. {how}"
    unit_info=time_unit_info(ctx.cfg) if ctx.active_stage>="S03" else None
    if unit_info and unit_info["status"]=="assumed_seconds":
        footer+=" Thời gian: giả định giây, chưa xác minh từ tác giả nguồn."
    if "n" in frame and not frame.empty:
        footer += f" N quan sát trong bảng: {frame['n'].min()}..{frame['n'].max()}."
    if population_n is not None:
        footer += f" N population={population_n}."
    if sample:
        footer += f" visualization sample n={sample['n']}, seed={sample['seed']}, rule={sample['rule']}"
    fig.text(.02,.015,"\n".join(textwrap.wrap(footer,width=145)),fontsize=8,va="bottom")
    target=ctx.path("figures/"+name+".png")
    with tempfile.TemporaryDirectory(prefix="pubg-figure-") as folder:
        temp=Path(folder)/"figure.png"
        fig.savefig(temp,dpi=130,bbox_inches="tight")
        publish(temp,target)
    plt.close(fig)
    ctx.record(target)
    ctx.json("figure_"+name,{"id":name,"path":target.relative_to(ctx.root).as_posix(),
        "source":table_path.relative_to(ctx.root).as_posix(),"source_sha256":digest(table_path),
        "title":title,"how_to_read":how,"unit":unit,"scope":ctx.scope,
        "sample":sample,"population_n":population_n,"analysis_scope":analysis_scope,
        "report_ready":ctx.scope=="full", "time_unit":unit_info})
    return target


def finalize(ctx):
    validated,hashes=set(),{}
    records={s:ctx.require(s,validated,hashes) for s in DEPENDENCIES["S10"]}
    tests=pd.read_csv(ctx.path("tables/model_metrics.csv"))
    expected={"s1_mean","s1_median","s1_linear","p2_mean","p2_median","p2_linear","t0_linear"}
    actual=set(tests.loc[tests["split"].eq("test") & tests["aggregation"].eq("micro"),"experiment"])
    if actual!=expected:
        raise ValueError(f"Missing/extra core experiments: {expected^actual}")
    clusters=read_json(ctx.path("manifests/clustering.json"))
    if not clusters["modes"]:
        raise ValueError("Không có RQ2 core mode")
    tables_required=["source_inventory","removal_ledger","split_summary","feature_dictionary",
                     "timing_audit","timing_coverage","eda_statistics","rq1_relationships",
                     "cluster_centers","cluster_sizes","cluster_outcomes","model_metrics",
                     "timing_comparison","error_analysis","coefficients"]
    for table in tables_required:
        if not ctx.path("tables/"+table+".csv").is_file():
            raise ValueError(f"Missing core table {table}")
    release_id=uuid.uuid4().hex
    release=ctx.path("manifests/releases/"+release_id)
    entries=[]
    selected=set()
    for record in records.values():
        for artifact in record["artifacts"]:
            source=ctx.root/artifact["path"]
            # Large data can be regenerated; release includes selected report/model evidence.
            if source.is_relative_to(ctx.out) and "checkpoints" not in source.parts:
                selected.add(source)
    selected.update([ctx.root/"configs/project.yaml",ctx.root/"PUBG_RESEARCH_SPEC.md",
                     ctx.root/"requirements.txt"])
    selected.update((ctx.root/"src").glob("*.py"))
    extra=sum(p.stat().st_size for p in selected)
    current=check_output_budget(ctx.root,ctx.cfg["storage"]["output_budget_gb"])
    # Check the complete copy before writing it, including a metadata allowance.
    needed=extra+1024**2
    if current+needed>ctx.cfg["storage"]["output_budget_gb"]*2**30 or needed>shutil.disk_usage(ctx.root).free:
        raise MemoryError(f"S10 release needs {needed/2**30:.2f} additional GiB; output budget/free disk insufficient")
    release.mkdir(parents=True,exist_ok=False)
    for source in sorted(selected):
        relative=source.relative_to(ctx.root)
        dest=release/relative
        dest.parent.mkdir(parents=True,exist_ok=True)
        shutil.copyfile(source,dest)
        if digest(dest)!=digest(source):
            raise IOError("Release copy checksum mismatch")
        entries.append({"path":relative.as_posix(),"sha256":digest(dest),"bytes":dest.stat().st_size})
    manifest={"format":1,"release_id":release_id,"project_id":ctx.cfg["project_id"],
              "scope":ctx.scope,"report_ready":ctx.scope=="full","spec_version":ctx.cfg["spec_version"],"time_unit":time_unit_info(ctx.cfg),
              "core_tables":tables_required,"core_experiments":sorted(expected),"stages":records,
              "optional":{"history":"not_requested","RF":"not_requested","C2_C4":"not_requested"},
              "entries":entries}
    write_json(manifest,release/"manifest.json")
    load_release(release/"manifest.json")
    ctx.record(release/"manifest.json")
    ctx.json("final_results",{"manifest":(release/"manifest.json").relative_to(ctx.root).as_posix(),
                              "release_id":release_id,"scope":ctx.scope,"report_ready":ctx.scope=="full"})


def load_release(path):
    """Reads exactly one frozen release; creates no files or directories."""
    path=Path(path).resolve()
    record=read_json(path)
    if record.get("format")!=1 or record.get("project_id")!="pubg-coursework-2026-v5" or not record.get("entries"):
        raise ValueError("Invalid or empty release manifest")
    files={}
    for entry in record["entries"]:
        artifact=(path.parent/entry["path"]).resolve()
        if not artifact.is_relative_to(path.parent) or not artifact.is_file() or digest(artifact)!=entry["sha256"]:
            raise ValueError(f"Release missing/corrupt/unsafe artifact: {entry['path']}")
        files[entry["path"]]=artifact
    unit_info=record.get("time_unit")
    if str(record.get("spec_version","")).startswith(("5.3-","5.4-","5.5-","5.6-","5.7-","5.8-","5.9-")) and unit_info is None:
        raise ValueError("Release 5.3 thiếu trạng thái/giới hạn đơn vị thời gian")
    if unit_info is not None:
        archived=time_unit_info(load_config(path.parent))
        key=f"outputs/{record['scope']}/manifests/time_unit.json"
        if unit_info!=archived or not unit_info["accepted"] or key not in files or read_json(files[key])!=unit_info:
            raise ValueError("Release time-unit metadata mismatch; không được nâng giả định thành verified")
    names={Path(k).stem for k in files if k.endswith(".csv")}
    required={"source_inventory","removal_ledger","split_summary","feature_dictionary","timing_audit",
              "timing_coverage","eda_statistics","rq1_relationships","cluster_centers","cluster_sizes",
              "cluster_outcomes","model_metrics","timing_comparison","error_analysis","coefficients"}
    if not required.issubset(names):
        raise ValueError("Release completeness failed")
    expected={"s1_mean","s1_median","s1_linear","p2_mean","p2_median","p2_linear","t0_linear"}
    model_names={Path(k).stem for k in files if k.endswith(".joblib")}
    prediction_names={Path(k).stem for k in files if k.endswith(".parquet")}
    if not expected.issubset(model_names) or not {"test_"+k for k in expected}.issubset(prediction_names):
        raise ValueError("Release core model/prediction completeness failed")
    metric_file=next(p for k,p in files.items() if Path(k).name=="model_metrics.csv")
    table=pd.read_csv(metric_file)
    if set(table.loc[table.split.eq("test") & table.aggregation.eq("micro"),"experiment"])!=expected:
        raise ValueError("Release test model coverage invalid")
    return record,files


def display_release(path):
    from IPython.display import Image,display
    record,files=load_release(path)
    display(pd.DataFrame([{k:record[k] for k in ("release_id","scope","report_ready","spec_version")}]))
    if not record["report_ready"]:
        print("DỮ LIỆU KIỂM THỬ: release này không phải kết quả PUBG chính thức.")
    if record.get("time_unit"):
        display(pd.DataFrame([record["time_unit"]]))
        if record["time_unit"]["status"]=="assumed_seconds":
            print("GIỚI HẠN ĐƠN VỊ: "+record["time_unit"]["limitation"])
    else:
        print("Release cũ không có trạng thái đơn vị tách biệt; không suy ra đơn vị đã verified.")
    for key,file in files.items():
        if file.suffix==".csv" and file.stem in record["core_tables"]:
            print(file.stem)
            display(pd.read_csv(file).head(25))
        elif file.suffix==".png":
            display(Image(filename=str(file)))
    return record



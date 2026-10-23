"""Update report evidence using full saved CSVs; never run research cells."""
from pathlib import Path
import hashlib,json,shutil
import pandas as pd
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

R=Path(__file__).resolve().parent
SNAP=R.parent/'results/PUBG_Coursework_v511_S09_S10'
OUT=SNAP/'outputs/full'
E=R/'evidence/full_results'
E.mkdir(parents=True,exist_ok=True)
inventory={x['path']:x for x in json.loads((SNAP/'handoff_full.json').read_text(encoding='utf8'))['entries']}
data={};audit=[];assets=[]
for path in sorted((OUT/'tables').glob('*.csv')):
    sha=hashlib.sha256(path.read_bytes()).hexdigest()
    assert sha==inventory[path.relative_to(SNAP).as_posix()]['sha256'],path.name
    rows=sum(len(c) for c in pd.read_csv(path,chunksize=50000))
    audit.append({'file':path.name,'rows':rows,'sha256':sha})
    if path.stem!='cluster_assignments':data[path.stem]=pd.read_csv(path)
for name in ['split','eda_scope','cluster_selection','selection','uncertainty','bins_s1','bins_p2','final_results']:
    source=OUT/'manifests'/(name+'.json')
    assert hashlib.sha256(source.read_bytes()).hexdigest()==inventory[source.relative_to(SNAP).as_posix()]['sha256']
    shutil.copyfile(source,E/source.name)

def esc(x):return str(x).replace('&',r'\&').replace('_',r'\_').replace('%',r'\%').replace('#',r'\#')
def table(name,source,cols,heads,caption,where=None):
    frame=data[source].copy()
    if where is not None:frame=where(frame)
    if (OUT/'tables'/(source+'.csv')).exists():shutil.copyfile(OUT/'tables'/(source+'.csv'),E/(source+'.csv'))
    else:frame.to_csv(E/(source+'.csv'),index=False)
    lines=[r'\begin{table}[H]\centering\small',r'\caption{'+caption+'}',r'\fitwidth{\begin{tabular}{'+'l'*len(cols)+'}',r'\toprule',' & '.join(heads)+r'\\\midrule']
    for row in frame[cols].itertuples(index=False,name=None):
        values=['NA' if pd.isna(v) else f'{v:.6g}' if isinstance(v,float) else str(v) for v in row]
        lines.append(' & '.join(map(esc,values))+r'\\')
    lines.extend([r'\bottomrule\end{tabular}}\end{table}',r'\source{\texttt{'+esc(source)+r'.csv}, số liệu đầy đủ đã lưu}'])
    (R/'tables'/(name+'.tex')).write_text('\n'.join(lines),encoding='utf8')
    assets.append({'table':name,'source':'evidence/full_results/'+source+'.csv','selected_rows':len(frame),'columns':cols})

table('inventory','source_inventory',['group','file','rows'],['Nhóm','Tệp','Số dòng'],'Kiểm kê toàn bộ tệp nguồn')
table('eda','eda_statistics',['feature','mean','median','max','missing'],['Biến','Trung bình','Trung vị','Lớn nhất','Thiếu'],'EDA train+validation, N = 57.262.855',lambda d:d[d.feature.isin(['player_kills','player_dmg','player_dist_walk','player_dist_ride','first_kill_time','player_survive_time','normalized_placement'])])
table('correlation','rq1_relationships',['feature','n','pearson','spearman'],['Đặc trưng','N','Pearson','Spearman'],'Quan hệ với placement, train+validation, Overall',lambda d:d[d['mode'].eq('Overall')&d.target.eq('normalized_placement')&d.feature.isin(['player_kills','player_dmg','player_dist_walk','player_dist_ride','total_distance','walk_ratio','avg_kill_time','early_kill_ratio','late_kill_ratio'])])
table('correlation_modes','rq1_relationships',['mode','n','pearson','spearman'],['Chế độ','N','Pearson','Spearman'],'Liên hệ giữa đi bộ và placement theo chế độ',lambda d:d[d.target.eq('normalized_placement')&d.feature.eq('player_dist_walk')])
table('clusters','cluster_sizes',['mode','cluster','profiles','share'],['Chế độ','Cụm','Hồ sơ','Tỷ trọng'],'Kích thước cụm của bản mô tả full')
table('validation','model_metrics',['experiment','n','mae','rmse','r2'],['Thí nghiệm','N','MAE','RMSE',r'$R^2$'],'Validation theo micro; survival và placement khác đơn vị',lambda d:d[d.split.eq('validation')&d.aggregation.eq('micro')])
for task in ['survival','placement']:
    target='player_survive_time' if task=='survival' else 'normalized_placement'
    table('test_'+task,'model_metrics',['experiment','n','mae','rmse','r2'],['Thí nghiệm','N','MAE','RMSE',r'$R^2$'],'Kết quả test '+task+' theo micro',lambda d:d[d.split.eq('test')&d.target.eq(target)&d.aggregation.eq('micro')])
table('timing','timing_comparison',['aggregation','metric','T0','T1','delta','n'],['Cách tính','Metric','T0','T1','Chênh lệch','N'],'Timing trên cùng cohort test; delta = T1 - T0')
table('errors','error_analysis',['experiment','group','n','mae','rmse','r2'],['Thí nghiệm','Nhóm','N','MAE','RMSE',r'$R^2$'],'Sai số test theo chế độ',lambda d:d[d['slice'].eq('mode')])
table('error_regions','error_analysis',['group','n','mae','rmse','r2'],['Miền placement','N','MAE','RMSE',r'$R^2$'],'Sai số placement theo miền mục tiêu, ngưỡng từ train',lambda d:d[d['slice'].eq('train_target_region')&d.experiment.eq('p2_linear')])
table('cohorts','model_cohorts',['task','split','rows','matches'],['Bài toán','Tập','Dòng','Trận'],'Cohort train/validation; T0 và P2 trùng cohort hash')
table('retention','profile_retention',['mode','total_profiles','retained','coverage','median_games'],['Chế độ','Tổng hồ sơ','Giữ lại','Tỷ lệ','Trung vị trận'],'Hồ sơ development với ngưỡng ít nhất 10 trận',lambda d:d[d.minimum_games.eq(10)])
table('k_selected','k_diagnostics',['mode','k','profiles','silhouette','seed_ari','min_cluster_share'],['Chế độ','K','Hồ sơ','Silhouette','ARI','Tỷ trọng nhỏ nhất'],'Chẩn đoán development tại K đã chọn; mẫu silhouette 2.000',lambda d:d[((d['mode']=='Duo')&(d.k==4))|((d['mode']=='Solo')&(d.k==2))|((d['mode']=='Squad')&(d.k==3))])
table('centers','cluster_centers',['mode','cluster','avg_kills','avg_damage','avg_walk','avg_assists'],['Chế độ','Cụm','Kill TB','Damage TB','Đi bộ TB','Hỗ trợ TB'],'Tâm cụm mô tả ở thang gốc')
table('coefficients','coefficients',['feature','coefficient'],['Đặc trưng P2','Hệ số chuẩn hóa'],'Một số hệ số P2, không phải tác động nhân quả',lambda d:d[d.experiment.eq('p2_linear')&d.feature.isin(['avg_kill_time','first_kill_time','player_dmg','walk_ratio','player_dbno','late_kills','late_kill_ratio'])])
table('feature_recipe','feature_dictionary',['feature','S1_predictor','P2_predictor','T0_predictor'],['Đặc trưng','S1','P2/T1','T0'],'Allowlist đầu vào từ registry',lambda d:d[d.S1_predictor|d.P2_predictor|d.T0_predictor])
coverage=data['timing_coverage'].groupby('timing_status',as_index=False).n_rows.sum()
coverage['percent']=coverage.n_rows/coverage.n_rows.sum()*100
data['coverage_summary']=coverage
table('coverage','coverage_summary',['timing_status','n_rows','percent'],['Trạng thái','Số dòng',r'Tỷ lệ (\%)'],'Độ bao phủ timing trên 67.369.231 dòng')
shutil.copyfile(OUT/'tables/timing_coverage.csv',E/'timing_coverage.csv')
assets[-1]['derived_from']='timing_coverage.csv: sum n_rows by status; percent of total'

plt.rcParams.update({'font.family':'DejaVu Sans','font.size':10})
fig,axes=plt.subplots(1,2,figsize=(10,3.7),layout='constrained')
metrics=data['model_metrics'];placement=metrics[metrics.target.eq('normalized_placement')&metrics.aggregation.eq('micro')]
experiments=['p2_mean','p2_median','t0_linear','p2_linear']
for ax,metric in zip(axes,['mae','rmse']):
    for shift,split,color in [(-.18,'validation','#4b7399'),(.18,'test','#bf8146')]:
        values=placement[placement.split.eq(split)].set_index('experiment').loc[experiments,metric]
        bars=ax.bar(np.arange(4)+shift,values,width=.36,label=split,color=color)
        ax.bar_label(bars,fmt='%.3f',fontsize=8,padding=2)
    ax.set_xticks(np.arange(4),['Mean','Median','T0','P2/T1']);ax.set_ylim(0,.35)
    ax.set_ylabel(metric.upper()+' (placement)');ax.legend(fontsize=8)
fig.savefig(R/'figures/placement_validation_test.png',dpi=180);plt.close(fig)
fig,axes=plt.subplots(1,2,figsize=(10,3.5),layout='constrained')
for mode,g in data['k_diagnostics'].groupby('mode'):
    axes[0].plot(g.k,g.silhouette,marker='o',label=mode)
    axes[1].plot(g.k,g.seed_ari,marker='o',label=mode)
for ax,label in zip(axes,['Silhouette (sample n=2000)','ARI across seeds']):
    ax.set_xlabel('K');ax.set_ylabel(label);ax.legend();ax.grid(alpha=.2)
fig.savefig(R/'figures/k_stability.png',dpi=180);plt.close(fig)
assets.extend([{'figure':'placement_validation_test.png','source':'evidence/full_results/model_metrics.csv'},{'figure':'k_stability.png','source':'evidence/full_results/k_diagnostics.csv'}])
summary={'csv_files_read':len(audit),'csv_inventory':audit,'assets':assets,'snapshot':str(SNAP.relative_to(R.parent))}
(E/'verification.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf8')
(R/'SOURCE_MAP.md').write_text('# Nguồn báo cáo hoàn thiện\n\nBảng lấy từ CSV đầy đủ, SHA256 khớp handoff. Hình cũ vẫn giữ ánh xạ notebook tại evidence/index.json.\n\n'+'\n'.join('- '+json.dumps(x,ensure_ascii=False) for x in assets),encoding='utf8')
print('Verified',len(audit),'full CSVs; built',len(assets),'mapped assets')

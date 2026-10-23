from pathlib import Path
import json
import pandas as pd
import fitz
R=Path(__file__).resolve().parent
items=json.loads((R/'evidence/index.json').read_text(encoding='utf8'))
(R/'tables').mkdir(exist_ok=True)
sources=[]
def esc(x):
    return str(x).replace('&',r'\&').replace('_',r'\_').replace('%',r'\%').replace('#',r'\#')
def table(name,label,cols,heads,caption,where=None,limit=None):
    candidates=[x for x in items if x.get('label')==label and 'table' in x]
    source=next((x for x in candidates if x['cell']==43),candidates[-1])
    df=pd.read_csv(R/source['table'])
    if where is not None:df=where(df)
    if limit:df=df.head(limit)
    df=df[cols]
    lines=[r'\begin{table}[H]\centering\small',r'\caption{'+caption+'}',r'\resizebox{\linewidth}{!}{\begin{tabular}{'+'l'*len(cols)+'}',r'\toprule',' & '.join(heads)+r'\\\midrule']
    for row in df.itertuples(index=False,name=None):
        values=[]
        for v in row:
            if pd.isna(v):s='NA'
            elif isinstance(v,float):s=f'{v:.6g}'
            else:s=str(v)
            values.append(esc(s))
        lines.append(' & '.join(values)+r'\\')
    lines += [r'\bottomrule\end{tabular}}',r'\end{table}',r'\source{'+esc(label)+', bảng hiển thị trong notebook đã chạy}']
    (R/'tables'/f'{name}.tex').write_text('\n'.join(lines).replace(r'\resizebox{\linewidth}{!}',r'\fitwidth'),encoding='utf8')
    sources.append((name,source))
table('inventory','source_inventory',['group','file','rows'],['Nhóm','Tệp','Số dòng'],'Kiểm kê 10 tệp nguồn')
table('eda','eda_statistics',['feature','mean','median','max','missing'],['Biến','Trung bình','Trung vị','Lớn nhất','Thiếu'],'Một số thống kê EDA; đơn vị thời gian là giả định',lambda d:d[d.feature.isin(['player_kills','player_dmg','player_dist_walk','player_dist_ride','first_kill_time','player_survive_time','normalized_placement'])])
table('correlation','rq1_relationships',['feature','target','n','pearson','spearman'],['Đặc trưng','Mục tiêu','N','Pearson','Spearman'],'Các cặp tương quan chọn từ bảng development',lambda d:d[d.feature.isin(['player_kills','player_dmg','player_dist_walk','first_kill_time'])])
table('clusters','cluster_sizes',['mode','cluster','profiles','share'],['Chế độ','Cụm','Hồ sơ','Tỷ trọng'],'Quy mô cụm trong kết quả mô tả full')
table('validation','model_metrics',['experiment','n','mae','rmse','r2'],['Thí nghiệm','N','MAE','RMSE',r'$R^2$'],'Kết quả validation theo micro; survival và placement khác đơn vị',lambda d:d[(d.split=='validation')&(d.aggregation=='micro')])
table('timing','timing_comparison',['aggregation','metric','T0','T1','delta','n'],['Cách tính','Metric','T0','T1','Chênh lệch','N'],'So sánh timing trên test; chênh lệch bằng T1 trừ T0')
table('errors','error_analysis',['experiment','group','n','mae','rmse','r2'],['Thí nghiệm','Nhóm','N','MAE','RMSE',r'$R^2$'],'Sai số test theo chế độ chơi',lambda d:d.slice=='mode' if False else d[d['slice']=='mode'])
groups={
'eda_selected': [('hist_player_survive_time_source','Phân phối thời gian sống trong EDA','Khoảng trục rất rộng phản ánh các giá trị cực đoan. Phần lớn dữ liệu bị dồn về vùng thấp; không diễn giải chiều cao cột như bằng chứng dữ liệu có thang đo đồng nhất.'),('eda_missing_source','Giá trị thiếu theo đặc trưng','Các tỷ số và thời điểm giao tranh có thiếu mang tính cấu trúc. Cần đọc định nghĩa mẫu số trước khi quyết định điền thiếu.')],
'correlation_selected':[('rq1_normalized_placement_source','Quan hệ hành vi với thứ hạng chuẩn hóa','Cần đọc dấu và độ lớn của cả Pearson và Spearman; sự liên hệ không chứng minh quan hệ nhân quả.')],
'clusters_selected':[('cluster_sizes_source','Phân bố kích thước cụm','Duo và Squad tập trung vào một cụm lớn. Các cụm cực nhỏ cần được xem như đối tượng kiểm tra bổ sung.'),('centers_Solo_source','Đặc trưng tương đối của hai cụm Solo','Các ô thể hiện thang tương đối trong hình nguồn; giá trị âm không có nghĩa số kill âm. Bảng tâm cụm ở thang gốc được dùng để mô tả hành vi.')],
'timing_selected':[('timing_delta_source','Chênh lệch đánh giá khi bổ sung timing','MAE và RMSE giảm, trong khi hệ số xác định tăng. Chưa có khoảng tin cậy để kết luận ý nghĩa thống kê.')],
'errors_selected':[('predicted_observed_p2_source','Dự đoán và thực tế của placement','Các điểm còn phân tán quanh đường chuẩn; mô hình có thông tin giải thích nhưng chưa dự đoán chính xác từng trường hợp.'),('predicted_observed_s1_source','Dự đoán và thực tế của survival','Thang dự đoán lệch rất xa thang thực tế ở nhiều điểm, có cả dự đoán âm. Kết quả này chưa phù hợp để sử dụng dự đoán thời gian sống.')]
}
for name,figs in groups.items():
    lines=[]
    for label,caption,comment in figs:
        source=next(x for x in items if x.get('label')==label and 'figure' in x)
        lines.append(r'\resultfigure{'+source['figure']+'}{'+caption+'}{'+comment+'}')
        sources.append((name,source))
    (R/'figures'/f'{name}.tex').write_text('\n'.join(lines),encoding='utf8')
doc=fitz.open(R.parent/'BaoCaoBTL_ML.pdf')
doc[0].get_pixmap(matrix=fitz.Matrix(3,3),clip=fitz.Rect(258,130,367,240)).save(R/'figures/logo.png')
(R/'SOURCE_MAP.md').write_text('# Nguồn bảng và hình\n\nChỉ số cell/output bắt đầu từ 0. CSV là dữ liệu hiển thị, có thể bị giới hạn số dòng.\n\n'+'\n'.join(f'- {name}: {x}' for name,x in sources),encoding='utf8')
print('Built',len(sources),'mapped assets')

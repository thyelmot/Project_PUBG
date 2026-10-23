from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib import font_manager
import pandas as pd
import numpy as np
ROOT=Path(__file__).resolve().parents[1]
E=ROOT/'pubg-report-evidence-20261023'
A=Path(__file__).resolve().parent
font_manager.fontManager.addfont('/System/Library/Fonts/Supplemental/Times New Roman.ttf')
plt.rcParams.update({'font.family':'Times New Roman','font.size':12,'axes.spines.top':False,'axes.spines.right':False,'figure.dpi':160})
def save(fig,name):
 fig.tight_layout();fig.savefig(A/name,dpi=200,bbox_inches='tight',facecolor='white');plt.close(fig)
df=pd.read_csv(E/'main/processed/train_class_counts.csv')
fig,ax=plt.subplots(figsize=(7.4,3.4)); b=ax.bar(df.weapon_group,df.fraction*100,color='#39618a',width=.62)
ax.set_ylabel('Tỷ lệ trên train (%)');ax.set_ylim(0,62)
for bar,v in zip(b,df.fraction):ax.text(bar.get_x()+bar.get_width()/2,bar.get_height()+1,f'{v*100:.2f}%'.replace('.',','),ha='center',fontsize=11)
save(fig,'train_class_distribution.png')
df=pd.read_csv(E/'main/validation/train_distance_by_class.csv')
fig,ax=plt.subplots(figsize=(7.4,3.4)); y=np.arange(len(df));med=df['50%'].to_numpy()
ax.errorbar(med,y,xerr=[med-df['25%'].to_numpy(),df['75%'].to_numpy()-med],fmt='o',color='#39618a',capsize=5,lw=2)
ax.set_yticks(y,df.weapon_group);ax.invert_yaxis();ax.set_xlabel('Khoảng cách (m)');ax.grid(axis='x',alpha=.2)
save(fig,'train_distance_iqr.png')
df=pd.read_csv(E/'main/test/ablation.csv')
fig,ax=plt.subplots(figsize=(7.4,3.5));v=df.macro_f1.to_numpy()
ax.bar(['A: Khoảng cách','B: + Thời gian','C: Ngữ cảnh','D: + Lịch sử'],v,color=['#aab5c2','#8196ae','#5b789a','#284f79'],width=.6)
ax.errorbar(range(4),v,yerr=[v-df.macro_f1_ci95_low.to_numpy(),df.macro_f1_ci95_high.to_numpy()-v],fmt='none',ecolor='black',capsize=6)
for i,n in enumerate(v):ax.text(i,n+.012,f'{n:.4f}'.replace('.',','),ha='center')
ax.set_ylabel('Macro-F1 trên test');ax.set_ylim(0,.49);save(fig,'ablation.png')
df=pd.read_csv(E/'main/test/confusion_matrix.csv',index_col=0);mat=df.to_numpy();norm=mat/mat.sum(axis=1)[:,None]
fig,ax=plt.subplots(figsize=(7,4.8));im=ax.imshow(norm,cmap='Blues',vmin=0,vmax=1)
for i in range(6):
 for j in range(6):ax.text(j,i,f'{norm[i,j]*100:.1f}%',ha='center',va='center',color='white' if norm[i,j]>.5 else 'black',fontsize=10)
ax.set_xticks(range(6),df.columns);ax.set_yticks(range(6),df.index);ax.set_xlabel('Nhãn dự đoán');ax.set_ylabel('Nhãn thật');fig.colorbar(im,ax=ax,fraction=.04,pad=.04);save(fig,'confusion_normalized.png')
df=pd.read_csv(E/'main/test/feature_importance.csv').sort_values('importance_mean')
fig,ax=plt.subplots(figsize=(8,5));ax.barh(df.feature,df.importance_mean,xerr=df.importance_std,color='#557b9e',capsize=2);ax.axvline(0,color='black',lw=.8);ax.set_xlabel('Mức giảm Macro-F1 sau xáo trộn');ax.tick_params(axis='y',labelsize=10);save(fig,'importance.png')
df=pd.read_csv(E/'appendix-c/appendix_alpha_tradeoff.csv')
fig,axes=plt.subplots(1,3,figsize=(10,3.7))
for family,label,color in [('random_forest','RF','#315e89'),('hist_gradient_boosting','HGB','#ab663f')]:
 d=df[df.family==family]
 for ax,col,title in zip(axes,['macro_f1','accuracy','minority_recall'],['Macro-F1','Accuracy','Minority Recall']):
  ax.plot(d.alpha,d[col],marker='o',label=label,color=color);ax.set_title(title);ax.set_xlabel('α');ax.grid(alpha=.2)
axes[0].legend();save(fig,'alpha_tradeoff.png')
fig,ax=plt.subplots(figsize=(8,3.3));ax.axis('off');boxes=[(.02,.64,'Dữ liệu gốc\nChọn 50.000 trận'),(.37,.64,'Làm sạch, chia trận\nTạo đặc trưng A-D'),(.72,.64,'Train\nFit pipeline'),(.72,.05,'Validation\nChọn và khóa mô hình'),(.37,.05,'Test một lần\nBootstrap theo trận'),(.02,.05,'Bảng, hình\nPhân tích và báo cáo')]
for x,y,t in boxes:ax.text(x+.12,y+.14,t,ha='center',va='center',fontsize=11,bbox=dict(boxstyle='round,pad=.6',fc='#f0f3f6',ec='#54718d'))
for a,b in [((.28,.78),(.34,.78)),((.63,.78),(.69,.78)),((.84,.52),(.84,.35)),((.69,.19),(.63,.19)),((.34,.19),(.28,.19))]:ax.annotate('',xy=b,xytext=a,arrowprops=dict(arrowstyle='->',color='#54718d',lw=1.5))
save(fig,'pipeline.png')

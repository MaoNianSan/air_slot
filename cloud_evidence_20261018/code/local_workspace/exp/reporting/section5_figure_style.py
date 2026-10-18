"""Purpose-driven Section 5 layouts; canvas widths include all text margins."""
import numpy as np
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D
from matplotlib.patches import Rectangle

BLUE='#0072B2'; ORANGE='#D55E00'; INK='#444444'; FAINT='#d7d7d7'
MIN_FONT=8.5

def style():
    plt.rcParams.update({'font.family':'DejaVu Serif','mathtext.fontset':'dejavuserif',
        'font.size':9,'axes.labelsize':9,'axes.titlesize':9.5,'xtick.labelsize':8.5,
        'ytick.labelsize':8.5,'legend.fontsize':8.5,'pdf.fonttype':42,'ps.fonttype':42,
        'axes.linewidth':.65,'xtick.major.width':.65,'ytick.major.width':.65})

def clean(ax):
    for side in ['top','right']: ax.spines[side].set_visible(False)
    ax.tick_params(length=3,pad=3)

def export(fig,number,figdir,outdir):
    # Fixed canvas: preserves nominal font sizes and repeatable manuscript scaling.
    fig.savefig(figdir/f'figure{number}.pdf')
    fig.savefig(outdir/f'FIGURE{number}.pdf')
    fig.savefig(figdir/f'figure{number}.svg')
    fig.savefig(figdir/f'figure{number}.png',dpi=220)
    plt.close(fig)

def boundary(rows,info,figdir,outdir):
    style(); fig=plt.figure(figsize=(6.8,4.05))
    gs=fig.add_gridspec(1,2,left=.085,right=.975,bottom=.25,top=.80,wspace=.28)
    labels={'both':'Selected by both','missed':'Missed by delay','added':'Added by delay','neither':'Not selected'}
    colors={'both':INK,'missed':ORANGE,'added':BLUE,'neither':FAINT}
    markers={'both':'o','missed':'^','added':'s','neither':'o'}
    for j,(st,lab) in enumerate([('PRE_IB','PRE'),('POST_IB_PRE_OB','TURN')]):
        ax=fig.add_subplot(gs[j]); data=[x for x in rows if x['stage_code']==st]; meta=info[st]
        k=meta['K']; m=meta['rank_max']; b=k+.5
        for xy,w,h,color in [((.5,.5),k,k,'#eeeeee'),((b,.5),m-k,k,'#fcf1e9'),((.5,b),k,m-k,'#eef5f9')]:
            ax.add_patch(Rectangle(xy,w,h,facecolor=color,edgecolor='none',zorder=0))
        for cat in ['neither','both','missed','added']:
            rr=[x for x in data if x['category']==cat]
            if rr: ax.scatter([x['delay_rank'] for x in rr],[x['consequence_rank'] for x in rr],
                marker=markers[cat],c=colors[cat],s=23 if cat in ['added','missed'] else 16,
                edgecolors='white',linewidths=.35,zorder=3)
        for x in data:
            if x['case_label']:
                # All changed nodes are inside the full boundary-focused window.
                offset=(4,-7) if x['case_label']=='M5' else (4,3)
                ax.annotate(x['case_label'],(x['delay_rank'],x['consequence_rank']),xytext=offset,
                    textcoords='offset points',fontsize=MIN_FONT,color=colors[x['category']],zorder=4)
        ax.axvline(b,color='0.45',lw=.8,ls=(0,(3,3))); ax.axhline(b,color='0.45',lw=.8,ls=(0,(3,3)))
        ax.set(xlim=(.5,m+.5),ylim=(m+.5,.5),xlabel='Delay-based rank',ylabel='Consequence-based rank' if j==0 else '')
        ticks=[1,2,3,4,5,6] if j==0 else [1,10,13,20,30,38]
        ax.set_xticks(ticks); ax.set_yticks(ticks); clean(ax)
        ax.set_title(f'({chr(97+j)}) {lab}',loc='left',fontweight='bold',pad=34)
        stat=f'N = {meta["N"]}, K = {k}   |   {len(meta["C"]-meta["D"])} replacements\n$L_{{att}}$ = {data[0]["L_att"]:.3f}'
        ax.text(0,1.035,stat,transform=ax.transAxes,fontsize=9,va='bottom')
    handles=[Line2D([],[],ls='',marker=markers[c],markersize=5,color=colors[c],label=labels[c]) for c in ['both','missed','added','neither']]
    fig.suptitle('Delay sufficiency at the Stage-I screening boundary',y=.985,fontsize=10.5,fontweight='bold')
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.52,.02),frameon=False,ncol=2,columnspacing=2.2,handletextpad=.5)
    export(fig,3,figdir,outdir)

def recoverability(case,selected,objmap,figdir,outdir):
    style(); fig=plt.figure(figsize=(6.8,4.95))
    # Landscape uses ~67% of usable width, profiles ~33%.
    left=fig.add_gridspec(1,3,left=.145,right=.635,bottom=.21,top=.86,width_ratios=[1.3,1.0,.09],wspace=.24)
    av=fig.add_subplot(left[0]); au=fig.add_subplot(left[1],sharey=av)
    rp=fig.add_gridspec(3,1,left=.755,right=.975,bottom=.21,top=.86,hspace=.72)
    profiles=[fig.add_subplot(rp[i]) for i in range(len(selected))]
    fig.suptitle('Recoverability after Stage-I screening',y=.99,fontsize=10.5,fontweight='bold')
    fig.text(.025,.945,'(a) Case-level recovery landscape',fontweight='bold',fontsize=9.5)
    fig.text(.73,.945,'(b) Objective profiles',fontweight='bold',fontsize=9.5)
    for a in [av,au]:
        a.set_ylim(len(case)-.5,-.5); clean(a); a.tick_params(axis='y',length=0)
        for y in range(len(case)):
            if y%2==0: a.axhspan(y-.5,y+.5,color='#f6f6f6',zorder=0)
    for y,x in enumerate(case):
        color=BLUE if x['stage']=='PRE' else ORANGE; marker='o' if x['stage']=='PRE' else 's'
        av.hlines(y,0,x['V'],color=color,lw=1.2,zorder=2)
        av.scatter([x['V']],[y],c=color,marker=marker,s=19,zorder=3)
        au.hlines(y,0,x['u_star'],color='0.80',lw=.75,zorder=1)
        au.scatter([x['u_star']],[y],facecolors='white' if x['u_star']==0 else color,
            edgecolors=color,marker=marker,s=24,linewidths=1,zorder=3)
    av.set_yticks(range(len(case)),[x['case_label'] for x in case]); au.tick_params(labelleft=False)
    av.set(xlim=(-.008,max(x['V'] for x in case)*1.09),xticks=[0,.1,.2,.3],xlabel='Recoverable value $V$')
    au.set(xlim=(-2,47),xticks=[0,15,30,45],xlabel='Recovery target $u^*$ (min)')
    av.set_title('Recoverable value',loc='left',pad=8); au.set_title('Optimal target',loc='left',pad=8)
    subtitles=['High recoverable value','Typical positive recovery','Optimal no-action case']
    for a,x,subtitle in zip(profiles,selected,subtitles):
        pairs=objmap[x['node_id']]['objective_by_action']; u=np.array([z[0] for z in pairs]); gap=np.array([z[1]-x['j_star'] for z in pairs])
        color=BLUE if x['stage']=='PRE' else ORANGE; marker='o' if x['stage']=='PRE' else 's'
        a.plot(u,gap,color=color,marker=marker,ms=3,lw=.9)
        optimum=[z[1]-x['j_star'] for z in pairs if z[0]==x['u_star']][0]
        a.scatter([x['u_star']],[optimum],s=32,marker=marker,facecolors='white' if x['u_star']==0 else color,edgecolors=color,zorder=4)
        a.axhline(0,color='.65',lw=.6); clean(a)
        a.set_title(f'{subtitle}\n{x["case_label"]} ({x["stage"]})',loc='left',fontsize=8.5,pad=5)
        a.set_xlim(-2,47); a.set_xticks([0,15,30,45]); a.set_ylabel('Objective gap',fontsize=8.5,labelpad=3)
        a.set_ylim(-max(gap)*.045,max(gap)*1.13); a.locator_params(axis='y',nbins=3)
    for a in profiles[:-1]: a.tick_params(labelbottom=False)
    profiles[-1].set_xlabel('Recovery target $u$ (min)',fontsize=8.5)
    handles=[Line2D([],[],ls='',marker='o',color=BLUE,label='PRE'),Line2D([],[],ls='',marker='s',color=ORANGE,label='TURN'),Line2D([],[],ls='',marker='o',markerfacecolor='white',markeredgecolor=INK,label='$u^*=0$')]
    fig.legend(handles=handles,loc='lower left',bbox_to_anchor=(.12,.065),frameon=False,ncol=3,handletextpad=.35,columnspacing=1.4)
    n=sum(x['stage']=='TURN' and x['u_star']==0 for x in case)
    fig.text(.15,.047,f'{n} TURN cases: $u^*=0$',fontsize=8.5)
    export(fig,4,figdir,outdir)

def information(rows,figdir,outdir):
    style(); fig=plt.figure(figsize=(7.6,3.05))
    gs=fig.add_gridspec(1,3,left=.18,right=.98,bottom=.27,top=.77,wspace=.24,width_ratios=[1,1,1.12])
    axs=[fig.add_subplot(gs[i]) for i in range(3)]; yy=np.arange(3)
    rowlabels=['History\ninformation\nremoved','Distribution\ncollapsed to\npoint estimate','Joint\ndependence\nremoved']
    for a in axs:
        a.set_ylim(2.55,-.55); a.set_yticks(yy); a.tick_params(axis='y',length=0,labelleft=False); clean(a)
        for i in range(3):
            if i%2==0: a.axhspan(i-.5,i+.5,color='#f5f5f5',zorder=0)
        a.spines['left'].set_visible(False)
    axs[0].tick_params(labelleft=True,pad=7); axs[0].set_yticklabels(rowlabels,fontsize=9)
    for a,key,lo,hi,title in [(axs[0],'L_att','L_att_lo','L_att_hi','(a) Stage-I\nscreening loss'),(axs[1],'L_rec','L_rec_lo','L_rec_hi','(b) Stage-II\nrecovery loss')]:
        for i,x in enumerate(rows):
            a.plot([x[lo],x[hi]],[i,i],color=INK,lw=1.2,zorder=2)
            a.plot([x[lo],x[lo]],[i-.065,i+.065],color=INK,lw=.8)
            a.plot([x[hi],x[hi]],[i-.065,i+.065],color=INK,lw=.8)
            a.scatter([x[key]],[i],c=INK,s=24,zorder=3)
        a.axvline(0,color='0.55',lw=.65); a.set_title(title,fontweight='bold',fontsize=9.5,pad=10)
        a.set_xlabel('$L_{att}$ (95% CI)' if key=='L_att' else '$L_{rec}$ (95% CI)')
        low=min(0,min(x[lo] for x in rows)); high=max(x[hi] for x in rows); pad=(high-low)*.10
        a.set_xlim(low-pad,high+pad)
    fig.suptitle('Decision value of information by decision layer',y=.98,fontsize=10.5,fontweight='bold')
    axs[0].set_xticks([0,.3,.6]); axs[1].set_xticks([0,.5,1,1.5])
    a=axs[2]; a.set_title('(c) Recovery-target\nagreement',fontweight='bold',fontsize=9.5,pad=10)
    for i,x in enumerate(rows):
        a.plot([x['A0'],x['A5']],[i,i],color='0.55',lw=1,zorder=2)
        # Nested symbols remain visible when the two agreements coincide.
        a.scatter([x['A0']],[i],facecolors='white',edgecolors=BLUE,marker='o',s=42,linewidths=1.25,zorder=3)
        a.scatter([x['A5']],[i],c=ORANGE,marker='D',s=14,zorder=4)
        a.text(x['A0'],i-.22,f"{x['A0_count']}/{x['R_star']}",ha='center',fontsize=8.5,color=BLUE)
        a.text(x['A5'],i+.32,f"{x['A5_count']}/{x['R_star']}",ha='center',fontsize=8.5,color=ORANGE)
    a.set(xlim=(0,1),xticks=[0,.5,1],xlabel='Agreement share')
    handles=[Line2D([],[],ls='',marker='o',markerfacecolor='white',markeredgecolor=BLUE,label='Exact target'),Line2D([],[],ls='',marker='D',color=ORANGE,markersize=4,label=r'Within $\pm5$ min')]
    fig.legend(handles=handles,loc='lower center',bbox_to_anchor=(.64,.025),frameon=False,ncol=2,columnspacing=1.5,handletextpad=.5)
    export(fig,5,figdir,outdir)







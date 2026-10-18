from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(r'D:\Local_Projects\airslot')
DATA = ROOT / 'backfill_20261014' / 'extracted'
OUT = ROOT / 'reports' / 'section5_candidate_20261017' / 'figures'
OUT.mkdir(parents=True, exist_ok=True)
YEARS = (2017, 2018, 2019, 2020, 2021, 2022)
YEAR_LABELS = ("'17", "'18", "'19", "'20", "'21", "'22")
VIEWS = ('DELAY', 'DELAY_PASSENGER', 'DELAY_DOWNSTREAM')
VIEW_LABELS = ('Delay', 'Delay + passenger exposure', 'Delay + downstream exposure')
COLORS = {'DELAY': '#0072B2', 'DELAY_PASSENGER': '#D55E00', 'DELAY_DOWNSTREAM': '#666666'}
MARKERS = {'DELAY': 'o', 'DELAY_PASSENGER': 's', 'DELAY_DOWNSTREAM': '^'}
CONTRASTS = {
    'HM--HJ': ('CROSS_STATE_DEPENDENCE', '#0072B2', 'o'),
    'HP--HJ': ('DISTRIBUTIONAL_INFORMATION', '#D55E00', 's'),
}
plt.rcParams.update({
    'font.family': 'DejaVu Sans', 'font.size': 8.5,
    'axes.labelsize': 8.2, 'axes.titlesize': 9.0,
    'xtick.labelsize': 7.6, 'ytick.labelsize': 7.6,
    'legend.fontsize': 7.6, 'pdf.fonttype': 42, 'ps.fonttype': 42,
    'figure.dpi': 300, 'savefig.dpi': 300, 'savefig.bbox': 'tight',
    'axes.spines.top': False, 'axes.spines.right': False,
    'axes.grid': True, 'grid.color': '#d9d9d9', 'grid.linewidth': 0.55,
    'grid.alpha': 0.7,
})

def read(name):
    return json.loads((DATA / name).read_text(encoding='utf-8'))

def save(fig, stem):
    fig.savefig(OUT / f'{stem}.pdf')
    fig.savefig(OUT / f'{stem}.png', dpi=300)
    plt.close(fig)

# Figure 5.1: year-specific q=.10 estimates and capacity-dependent incremental difference.
e1 = read('e1_six_year.json')
fig, axs = plt.subplots(2, 2, figsize=(8.2, 5.35), gridspec_kw={'height_ratios': [1.0, 1.0]})
for col, stage in enumerate(('PRE', 'TURN')):
    ax = axs[0, col]
    x = np.arange(len(YEARS))
    offsets = {'DELAY': -0.18, 'DELAY_PASSENGER': 0.0, 'DELAY_DOWNSTREAM': 0.18}
    for view in VIEWS:
        vals, lo, hi = [], [], []
        for year in YEARS:
            r = next(z for z in e1[str(year)]['q_grid'] if z['stage'] == stage and z['view'] == view and abs(z['q'] - .10) < 1e-10)
            vals.append(r['attention_loss']); lo.append(r['ci_low']); hi.append(r['ci_high'])
        vals, lo, hi = map(np.asarray, (vals, lo, hi))
        ax.errorbar(x + offsets[view], vals, yerr=np.vstack((vals-lo, hi-vals)),
                    fmt=MARKERS[view], color=COLORS[view], ms=4.3, capsize=2.0,
                    elinewidth=.9, linestyle='none', label=VIEW_LABELS[VIEWS.index(view)])
    ax.set_title(f'({"a" if col == 0 else "b"}) {stage}, q = 0.10')
    ax.set_ylabel(r'$L^{\mathrm{att}}$')
    ax.set_xticks(x, YEAR_LABELS)
    ax.set_ylim(0, .24); ax.set_yticks(np.arange(0, .241, .06))
    ax.grid(axis='x', visible=False)

qvals = (.05, .10, .20, .30)
for col, stage in enumerate(('PRE', 'TURN')):
    ax = axs[1, col]
    all_year_vals = []
    for year in YEARS:
        row = []
        for q in qvals:
            delay = next(z['attention_loss'] for z in e1[str(year)]['q_grid'] if z['stage'] == stage and z['view'] == 'DELAY' and abs(z['q']-q) < 1e-10)
            passenger = next(z['attention_loss'] for z in e1[str(year)]['q_grid'] if z['stage'] == stage and z['view'] == 'DELAY_PASSENGER' and abs(z['q']-q) < 1e-10)
            row.append(delay - passenger)
        all_year_vals.append(row)
    arr = np.asarray(all_year_vals)
    mean, low, high = arr.mean(axis=0), arr.min(axis=0), arr.max(axis=0)
    ax.fill_between(qvals, low, high, color='#56B4E9', alpha=.25, linewidth=0,
                    label='Annual min–max (not a CI)')
    ax.plot(qvals, mean, marker='o', color='#0072B2', lw=1.8, ms=4.5,
            label='Equal-year mean')
    ax.axhline(0, color='#555555', lw=.8, ls='--')
    ax.set_title(f'({"c" if col == 0 else "d"}) {stage}: incremental difference by review fraction')
    ax.set_xlabel('Review fraction, q')
    ax.set_ylabel(r'$\Delta L^{\mathrm{att}}$')
    ax.set_xticks(qvals, [f'{q:.2f}' for q in qvals]); ax.set_ylim(-.04, .11)
    ax.grid(axis='x', visible=False)
handles, labels = axs[0, 0].get_legend_handles_labels()
fig.legend(handles, labels, loc='upper center', ncol=3, frameon=False, bbox_to_anchor=(.5, 1.015), columnspacing=1.4, handletextpad=.35)
axs[1, 1].legend(loc='upper right', frameon=False, fontsize=7.0)
fig.subplots_adjust(left=.085, right=.985, bottom=.105, top=.87, hspace=.42, wspace=.24)
save(fig, 'figure_5_1_capacity_and_screening')

# Figure 5.2: four-panel direct comparisons to HJ. HP--HM paired increments are excluded
# because they use a distinct paired-support sample.
e2 = read('e2_six_year.json')
fig, axs = plt.subplots(2, 2, figsize=(8.0, 5.35))
x = np.arange(len(YEARS))
offsets = {'HM--HJ': -0.09, 'HP--HJ': 0.09}
panel_specs = [
    ('stage1_reassigned_share', 'Stage-I shortlist positions reassigned', 'Share of HJ shortlist (%)', 0, 100, 'a'),
    ('L_att', 'Stage-I normalized reference loss', r'$L^{\mathrm{att}}$', 0, .62, 'b'),
    ('A0', 'Stage-II exact target agreement', r'$A_0$', 0, 1.0, 'c'),
    ('L_rec', 'Stage-II normalized reference loss', r'$L^{\mathrm{rec}}$', 0, 1.05, 'd'),
]
for ax, (metric, title, ylabel, ymin, ymax, letter) in zip(axs.flat, panel_specs):
    for contrast, (key, color, marker) in CONTRASTS.items():
        vals, lows, highs = [], [], []
        for year in YEARS:
            r = e2[str(year)]['e2']['information_value'][key]
            if metric == 'stage1_reassigned_share':
                value = r[metric] * 100; low = high = value
            else:
                value = r[metric]
                lo_key, hi_key = metric + '_ci_low', metric + '_ci_high'
                low, high = r.get(lo_key, value), r.get(hi_key, value)
            vals.append(value); lows.append(low); highs.append(high)
        vals, lows, highs = map(np.asarray, (vals, lows, highs))
        pos = x + offsets[contrast]
        if metric in ('L_att', 'L_rec'):
            ax.errorbar(pos, vals, yerr=np.vstack((vals-lows, highs-vals)),
                        fmt=marker, color=color, ms=4.1, capsize=1.8,
                        elinewidth=.85, linestyle='none', label=contrast)
        else:
            ax.plot(pos, vals, linestyle='none', marker=marker, color=color,
                    ms=4.2, label=contrast)
    ax.set_title(f'({letter}) {title}', loc='left')
    ax.set_ylabel(ylabel); ax.set_ylim(ymin, ymax)
    ax.set_xticks(x, YEAR_LABELS); ax.grid(axis='x', visible=False)
    if metric == 'stage1_reassigned_share': ax.set_yticks([0,25,50,75,100])
    elif metric in ('A0', 'L_rec'): ax.set_yticks([0,.25,.5,.75,1.0])
handles = [Line2D([0],[0],marker=CONTRASTS[c][2],color='none',markerfacecolor=CONTRASTS[c][1],
                  markeredgecolor=CONTRASTS[c][1],markersize=4.5,label=c) for c in CONTRASTS]
fig.legend(handles=handles, loc='upper center', ncol=2, frameon=False,
           bbox_to_anchor=(.5, 1.01), columnspacing=1.8, handletextpad=.4)
fig.subplots_adjust(left=.09, right=.985, bottom=.09, top=.88, hspace=.42, wspace=.28)
save(fig, 'figure_5_2_information_layers')

# Figure 5.3: annual objective-specific exact agreement and conditional target shift.
e3 = read('e3_six_year.json')
objectives = ('BALANCED', 'FLIGHT', 'PASSENGER', 'RESOURCE')
objlabels = ('Balanced', 'Flight', 'Passenger', 'Resource')
agreement = np.array([[e3[str(y)]['profile_summary'][o]['exact_target_agreement_share'] for y in YEARS] for o in objectives])
conditional = np.array([
    [e3[str(y)]['profile_summary'][o]['mean_abs_target_change_min'] /
     max(1e-12, 1 - e3[str(y)]['profile_summary'][o]['exact_target_agreement_share']) for y in YEARS]
    for o in objectives
])
fig, axs = plt.subplots(1, 2, figsize=(8.0, 3.45), gridspec_kw={'wspace': .48})
for ax, matrix, title, cbar_label, vmin, vmax, fmt in [
    (axs[0], agreement, '(a) Exact target agreement', 'Agreement share', .50, .80, '.2f'),
    (axs[1], conditional, '(b) Mean target shift when targets differ', 'Conditional mean |Δu*| (min)', 0, 14, '.1f'),
]:
    im = ax.imshow(matrix, cmap='viridis', aspect='auto', vmin=vmin, vmax=vmax)
    ax.grid(False)
    ax.set_title(title); ax.set_xticks(range(len(YEARS)), YEAR_LABELS)
    ax.set_yticks(range(len(objectives)), objlabels); ax.set_xlabel('Evaluation year')
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            val = matrix[i,j]
            norm = (val-vmin)/(vmax-vmin)
            ax.text(j, i, format(val, fmt), ha='center', va='center',
                    color='white' if norm < .56 else '#111111', fontsize=8.2)
    cbar = fig.colorbar(im, ax=ax, fraction=.045, pad=.035)
    cbar.set_label(cbar_label)
fig.subplots_adjust(left=.12, right=.97, bottom=.17, top=.87)
save(fig, 'figure_5_3_objectives')
print('Created candidate figures in', OUT)


from pathlib import Path
import json
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

ROOT = Path(r'D:\Local_Projects\airslot\backfill_20261014')
DATA = ROOT / 'extracted' / 'e2_six_year.json'
OUT = ROOT / 'figures'
YEARS = (2017, 2018, 2019, 2020, 2021, 2022)
YEAR_LABELS = ("'17", "'18", "'19", "'20", "'21", "'22")
KEYS = {
    'HM--HJ': 'CROSS_STATE_DEPENDENCE',
    'HP--HJ': 'DISTRIBUTIONAL_INFORMATION',
    'HP--HM paired increment': 'MARGINAL_UNCERTAINTY',
}
COLORS = {
    'HM--HJ': '#0072B2',
    'HP--HJ': '#D55E00',
    'HP--HM paired increment': '#009E73',
}
MARKERS = {'HM--HJ': 'o', 'HP--HJ': 's', 'HP--HM paired increment': '^'}
OFFSETS = {'HM--HJ': -0.10, 'HP--HJ': 0.0, 'HP--HM paired increment': 0.10}

plt.rcParams.update({
    'font.size': 7.5,
    'axes.titlesize': 8.0,
    'axes.labelsize': 7.5,
    'legend.fontsize': 7.0,
    'xtick.labelsize': 6.8,
    'ytick.labelsize': 6.8,
    'figure.dpi': 300,
    'savefig.bbox': 'tight',
    'axes.grid': True,
    'grid.alpha': 0.22,
    'grid.linewidth': 0.45,
    'axes.spines.top': False,
    'axes.spines.right': False,
})

def main():
    data = json.loads(DATA.read_text(encoding='utf-8'))
    x = np.arange(len(YEARS))
    fig, axes = plt.subplots(1, 3, figsize=(7.1, 2.75))

    # Panel A: shortlist position replacement; annual estimates are not connected.
    ax = axes[0]
    for contrast in ('HM--HJ', 'HP--HJ'):
        rows = [data[str(y)]['e2']['information_value'][KEYS[contrast]] for y in YEARS]
        values = np.array([r['stage1_reassigned_share'] * 100 for r in rows])
        ax.plot(x + OFFSETS[contrast], values, linestyle='none',
                marker=MARKERS[contrast], markersize=4.0,
                color=COLORS[contrast])
    hm_values = [data[str(y)]['e2']['information_value'][KEYS['HM--HJ']]['stage1_reassigned_share'] * 100 for y in YEARS]
    ax.text(0.04, 0.27, f"HM--HJ: {min(hm_values):.1f}--{max(hm_values):.1f}%",
            transform=ax.transAxes, fontsize=6.4, color=COLORS['HM--HJ'],
            bbox=dict(boxstyle='round,pad=0.22', facecolor='white', edgecolor='#b7cbd8', linewidth=0.5))
    ax.set_title('(a) Stage-I positions reassigned')
    ax.set_ylabel('Share of reference shortlist (%)')
    ax.set_ylim(0, 100)
    ax.set_yticks([0, 25, 50, 75, 100])
    ax.set_xticks(x, YEAR_LABELS)
    ax.grid(axis='x', visible=False)

    # Panel B: exact target agreement. No interval is shown because the retained output
    # provides point estimates for A0 but no corresponding bootstrap interval.
    ax = axes[1]
    for contrast in ('HM--HJ', 'HP--HJ'):
        rows = [data[str(y)]['e2']['information_value'][KEYS[contrast]] for y in YEARS]
        values = np.array([r['A0'] for r in rows])
        ax.plot(x + OFFSETS[contrast], values, linestyle='none',
                marker=MARKERS[contrast], markersize=4.0,
                color=COLORS[contrast])
    ax.set_title('(b) Stage-II exact target agreement')
    ax.set_ylabel('$A_0$')
    ax.set_ylim(0, 1)
    ax.set_yticks([0, .25, .50, .75, 1.0])
    ax.set_xticks(x, YEAR_LABELS)
    ax.grid(axis='x', visible=False)

    # Panel C: normalized recovery loss; the only outcome here with retained CIs.
    ax = axes[2]
    for contrast, key in KEYS.items():
        rows = [data[str(y)]['e2']['information_value'][key] for y in YEARS]
        values = np.array([r['L_rec'] for r in rows])
        lows = np.array([r['L_rec_ci_low'] for r in rows])
        highs = np.array([r['L_rec_ci_high'] for r in rows])
        ax.errorbar(
            x + OFFSETS[contrast], values,
            yerr=np.vstack((values - lows, highs - values)),
            fmt=MARKERS[contrast], markersize=4.0,
            color=COLORS[contrast], capsize=1.8, elinewidth=0.8,
            linestyle='none',
        )
    ax.set_title('(c) Stage-II normalized reference loss')
    ax.set_ylabel('$L^{\\mathrm{rec}}$')
    ax.set_ylim(0, 1.05)
    ax.set_yticks([0, .25, .50, .75, 1.0])
    ax.set_xticks(x, YEAR_LABELS)
    ax.grid(axis='x', visible=False)

    handles = [Line2D([0], [0], marker=MARKERS[c], color='none',
                      markerfacecolor=COLORS[c], markeredgecolor=COLORS[c],
                      markersize=4.2, label=c) for c in KEYS]
    fig.legend(handles=handles, loc='upper center', ncol=3, frameon=False,
               bbox_to_anchor=(0.5, 1.04), columnspacing=1.2, handletextpad=0.35)
    fig.subplots_adjust(left=0.08, right=0.99, bottom=0.20, top=0.78, wspace=0.52)
    OUT.mkdir(parents=True, exist_ok=True)
    fig.savefig(OUT / 'figure_s5_2_information_layers_v2.pdf')
    fig.savefig(OUT / 'figure_s5_2_information_layers_v2.png')
    plt.close(fig)
    print(OUT / 'figure_s5_2_information_layers_v2.pdf')
    print(OUT / 'figure_s5_2_information_layers_v2.png')

if __name__ == '__main__':
    main()
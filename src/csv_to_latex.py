import pandas as pd
import matplotlib.pyplot as plt
import seaborn as sns
import os
from collections import defaultdict
import matplotlib.colors as mcolors
import re
import numpy as np

RESULT_TEX = os.path.join("D:", "results", "final", "result.tex")

sns.set_theme()
data_path = os.path.join("D:", "final")
result_path = os.path.join("D:", "results", "final")

metric_name_translator = {
    'adjusted_mutual_info_score': 'AMI',
    'few_shot_accuracy_cluster_nn': 'CCA',
    'ap_avg': "Avg AP",
    'aow0.0': "SPACE-Flow",
    'aow10.0': "SPACE-Time",
    'baseline': "SPACE",
    'relevant_': "Relevant ",
    'space_invaders': "Space Invaders",
    'pong': "Pong",
    'mspacman': "Ms Pacman",
    'tennis': "Tennis",
    'air_raid': "Air Raid",
    'boxing': "Boxing",
    'carnival': "Carnival",
    'riverraid': "Riverraid",
    'f_score': "F-Score",
}


def translate(name):
    for k, v in metric_name_translator.items():
        name = re.sub(k, v, name)
    return name.replace("_", "\\_")


def group_by(col, key_extractor):
    result = defaultdict(list)
    for e in col:
        result[key_extractor(e)].append(e)
    return result


def sub_group_by(experiments, key_extractor):
    result = defaultdict(dict)
    for e in experiments:
        extracted = key_extractor(e)
        result[extracted][e.replace(extracted + "_", "")] = experiments[e]
    return result


def prepare_mean_std(experiments):
    columns = []
    first = True
    for k, directories in experiments.items():
        sub_dfs = [pd.read_csv(os.path.join(data_path, d, "metrics.csv"), sep=";") for d in directories]

        for sub_df in sub_dfs:
            add_contrived_columns(sub_df)
        if first:
            columns.append(sub_dfs[0]['global_step'])
            first = False
        for metric in sub_dfs[0]:
            concat_over_seeds = pd.concat([d[metric] for d in sub_dfs], axis=1)
            mean = concat_over_seeds.mean(axis=1)
            mean.name = f'{k}_{metric}_mean'
            std = concat_over_seeds.std(axis=1)
            std.name = f'{k}_{metric}_std'
            columns.extend([mean, std])
    df = pd.concat(columns, axis=1)
    return df


figure = """
\\begin{{subfigure}}{{.45\\textwidth}}
  \\centering
  \\includegraphics[width=\\textwidth]{{{1}}}
  \\caption{{{0}}}
  \\label{{fig:{2}}}
\\end{{subfigure}}
"""


def bar_plot(experiments, key, joined_df, title=None, caption="A plot of ...", group_key="space_invaders"):
    import matplotlib
    print(matplotlib.__version__)
    plt.clf()
    labels = experiments.keys()
    x = np.arange(len(labels))
    width = 0.8
    fig, ax = plt.subplots()
    bars = []
    styles = experiments[group_key]
    last_row = joined_df.iloc[-1]
    for i, expis in enumerate(styles):
        bars.append(ax.bar(x - width / 2 + width * (i + 0.5) / len(styles),
                           [last_row[f'{game}_{expis}_{key}_mean'] for game in experiments],
                           width / len(styles),
                           yerr=[last_row[f'{game}_{expis}_{key}_std'] for game in experiments],
                           capsize=3, label=expis))
    ax.set_ylabel(key)
    ax.set_title(f'{key} by game and variant of SPACE')
    ax.set_xticks(x, labels)
    ax.legend()
    for b in bars:
        ax.bar_label(b, padding=3)
    fig.tight_layout()
    save_and_tex(caption, key, "bar")


def save_and_tex(caption, key, kind="line"):
    img_path = os.path.join(result_path, "img", f"{caption}_{kind}_{key}.png")
    if os.path.exists(img_path):
        os.remove(img_path)
    plt.savefig(img_path, bbox_inches="tight")
    plt.clf()
    with open(RESULT_TEX, "a") as tex:
        tex.write(figure.format(caption, f"img/{caption}_{kind}_{key}", key))
        tex.write("\n")


def line_plot(experiment_groups, key, joined_df, title=None, caption="A plot of ..."):
    plt.clf()
    for game in experiment_groups:
        plt.figure(figsize=(12, 7))
        plt.ylim((-0.1, 1.1))
        plt.yticks([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])
        for c, expis in zip(mcolors.TABLEAU_COLORS, experiment_groups[game]):
            plt.plot(joined_df['global_step'], joined_df[f'{game}_{expis}_{key}_mean'], color=c, label=f"{translate(expis)}")
            plt.fill_between(joined_df['global_step'], joined_df[f'{game}_{expis}_{key}_mean'] - joined_df[f'{game}_{expis}_{key}_std'],
                             joined_df[f'{game}_{expis}_{key}_mean'] + joined_df[f'{game}_{expis}_{key}_std'], alpha=0.5, color=c)
        plt.legend(loc="lower right")
        save_and_tex(translate(game), key)

from matplotlib.colors import LinearSegmentedColormap
import matplotlib.colors as mcolors


def my_cmap(colors):
    nodes = [0.0, 1.0]
    return LinearSegmentedColormap.from_list("mycmap", list(zip(nodes, colors)), N=256)

def pr_plot(experiment_groups, joined_df):
    plt.clf()
    dth = 0.1
    for game in experiment_groups:
        plt.figure(figsize=(12, 7))

        plt.ylim((-0.1, 1.1))
        plt.yticks([0.0, 0.2, 0.4, 0.6, 0.8, 1.0])

        for c, expis in zip(mcolors.TABLEAU_COLORS, experiment_groups[game]):
            x = joined_df[f'{game}_{expis}_relevant_recall_mean'].to_numpy()
            y = joined_df[f'{game}_{expis}_relevant_precision_mean'].to_numpy()
            x_err = joined_df[f'{game}_{expis}_relevant_recall_std'].to_numpy()
            y_err = joined_df[f'{game}_{expis}_relevant_precision_std'].to_numpy()
            x_ = x[1:] - x[:-1]
            y_ = y[1:] - y[:-1]
            dist = np.sqrt(x_**2 + y_**2)

            high = np.array(mcolors.to_rgb(c))
            red = my_cmap((high * 0.2, high))
            colors = red(np.linspace(0, 1, len(x)))
            colors2 = red(np.linspace(0, 1, len(x[4::5])))
            plt.scatter(x[4::5], y[4::5], c=colors2, zorder=3, edgecolors='black', alpha=0.8)
            plt.scatter(x, y, c=colors, zorder=3, edgecolors='black', alpha=0.2)
            for xe, ye, ex, ey, ec in zip(x[4::5], y[4::5], x_err[4::5], y_err[4::5], colors):
                plt.errorbar(xe, ye, xerr=ex, yerr=ey, fmt='none', ecolor=ec, capsize=4)
            # plt.quiver(x[:-1][dist > dth], y[:-1][dist > dth], x_[dist > dth],
            #            y_[dist > dth], np.linspace(0, 1, len(x) - 1)[dist > dth],
            #            angles='xy', width=0.003, scale_units='xy', scale=1,
            #            linewidth=1, edgecolor='#00000080', cmap=red, zorder=4)
            prs = np.stack((x, y), axis=1)
            print(prs)
            bounds = np.array([pr for pr in prs if all(not all(pr2 > pr) for pr2 in prs)])
            bounds_ind = np.argsort(bounds[:, 0])
            bounds = bounds[bounds_ind]
            bounds = np.insert(bounds, 0, [0.0, bounds[0, 1]], axis=0)
            bounds = np.append(bounds, [[bounds[-1, 0], 0.0]], axis=0)
            plt.plot(bounds[:, 0], bounds[:, 1], linestyle='dotted', c=c, zorder=5)
            plt.plot(x, y, linestyle='dotted', c=c, zorder=0, alpha=0.2)
        plt.legend(loc="lower left")
        save_and_tex(translate(game), "Precision-Recall Curve", kind="Quiver")


table_tex = """
\\begin{{table}}[h]
\\centering
\\begin{{tabular}}{{{4}}}
\\hline
{0} \\\\
\\hline
{1} \\\\
\\hline
\\end{{tabular}}
\\caption{{{2}}}
\\label{{table:{3}}}
\\end{{table}}
"""


def table(experiment_groups, columns, joined_df, at=None, caption=None):
    if at is None:
        at = [int(joined_df.loc[len(joined_df) - 1]["global_step"].item())]
    if caption is None:
        caption = "A table showcasing " + ", ".join(columns[:-1]) + f" and {columns[-1]}."
        caption = caption.replace("_", "\\_")
    header = " & ".join(["Game", "Configuration"] + [translate(c) for c in columns]).replace("_", "\\_")
    content = []
    for game in experiment_groups:
        for expi in experiment_groups[game]:
            content.append(" & ".join(
                [game.replace("_", "\\_"), translate(expi.replace("_", "\\_"))] + [
                    f'{joined_df.loc[joined_df["global_step"] == idx][game + "_" + expi + "_" + c + "_mean"].item():.3f} '
                    f'\\pm {joined_df.loc[joined_df["global_step"] == idx][game + "_" + expi + "_" + c + "_std"].item():.3f}'
                    for c in columns for idx in at]))
    with open(RESULT_TEX, "a") as tex:
        tex.write(table_tex.format(header, " \\\\ \n".join(content), caption, ";".join(columns),
                                   "c".join(["|"] * (len(columns) + 3))))
        tex.write("\n")


table_metric_tex = """
\\begin{{table}}[h]
\\centering
\\begin{{tabular}}{{{4}}}
\\hline
\\multicolumn{{{6}}}{{|c|}}{{\\textbf{{{5}}}}} \\\\
\\hline
\\hline
{0} \\\\
\\hline
{1} \\\\
\\hline
\\end{{tabular}}
\\caption{{{2}}}
\\label{{table:{3}}}
\\end{{table}}
"""


def bf(name):
    return f'\\textbf{{{name}}}'


def table_entry(joined_df, idx, game, c, metric, variants):
    all_mean = [joined_df.loc[joined_df["global_step"] == idx][game + "_" + v + "_" + metric + "_mean"].item() for v in variants]

    mean = joined_df.loc[joined_df["global_step"] == idx][game + "_" + c + "_" + metric + "_mean"].item()
    std = joined_df.loc[joined_df["global_step"] == idx][game + "_" + c + "_" + metric + "_std"].item()
    if mean > 0.99 * np.max(all_mean):
        return f'\\textbf{{{mean :.3f} $\\pm$ {std :.3f}}}'
    return f'{mean :.3f} $\\pm$ {std :.3f}'

def table_by_metric(experiment_groups, columns, joined_df, at=None, caption=None, group_key="space_invaders"):
    if at is None:
        at = [int(joined_df.loc[len(joined_df) - 1]["global_step"].item())]
    for metric in columns:
        header = " & ".join([bf("Configuration")] + [bf(translate(c)) for c in experiment_groups[group_key]])
        if caption is None:
            caption = f"A table showcasing {metric}."
            caption = translate(caption)
        content = []
        for game in experiment_groups:
            content.append(" & ".join(
                [bf(translate(game))] + [
                    table_entry(joined_df, idx, game, c, metric, experiment_groups[group_key])
                    for c in experiment_groups[group_key] for idx in at]))
        with open(RESULT_TEX, "a") as tex:
            tex.write(table_metric_tex.format(header, " \\\\ \n".join(content), caption, ";".join([metric]),
                                              ("c".join(["|"] * (len(experiment_groups) + 2)).replace('|', '||', 2).replace('||', '|', 1)),
                                              translate(metric), 4))
            tex.write("\n")


def add_contrived_columns(df):
    for style in ['relevant', 'all', 'moving']:
        aps = df.filter(regex=f'{style}_ap')
        df[f'{style}_ap_avg'] = aps.mean(axis=1)
        df[f'{style}_f_score'] = 2 * df[f'{style}_precision'] * df[f'{style}_recall'] / (df[f'{style}_precision'] + df[f'{style}_recall'] + 1e-8)
    return df



def select_game(expi):
    for game in ['air_raid', 'boxing', 'carnival', 'mspacman', 'pong', 'riverraid', 'space_invaders', 'tennis']:
        if game in expi:
            return game
    raise ValueError(f'{expi} does not contain any of the known games...')


def main():
    if os.path.exists(RESULT_TEX):
        os.remove(RESULT_TEX)
    os.makedirs(result_path, exist_ok=True)
    os.makedirs(result_path + "\\img", exist_ok=True)
    files = os.listdir(data_path)
    experiments = group_by(files,
                           lambda f: f.split("_seed")[0] + ("_" if f.split("_seed")[1][2:] else "") + f.split("_seed")[
                                                                                                          1][2:])
    joined_df = prepare_mean_std(experiments)
    experiment_groups = sub_group_by(experiments, select_game)
    mutual_info_columns = ["relevant_precision", "relevant_recall", "relevant_f_score"]
    desired_experiment_order = ['air_raid', 'boxing', 'carnival', 'mspacman', 'pong', 'riverraid', 'space_invaders', 'tennis']
    experiment_groups = {k: experiment_groups[k] for k in desired_experiment_order if k in experiment_groups}
    # bar_plot(experiment_groups, "relevant_few_shot_accuracy_with_4", joined_df)
    table_by_metric(experiment_groups, mutual_info_columns, joined_df)
    # line_plot(experiments, "relevant_ap_avg", joined_df)
    line_plot(experiment_groups, "relevant_f_score", joined_df)
    pr_plot(experiment_groups, joined_df)
    print("Plotting completed")


if __name__ == '__main__':
    main()
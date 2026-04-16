#!/usr/bin/env python3
"""
AB实验分析模板
复制此文件，填入实际数据后运行
"""
import numpy as np
from scipy import stats


def analyze_experiment():
    """
    完整分析模板 — 复制后修改数据即可
    """

    # ============================================================
    # 1. 填入数据
    # ============================================================

    # 稳定期日期
    dates = ['4/8', '4/9', '4/10', '4/11', '4/12']

    # 活跃用户数（用于归一化）
    active_users = {
        0: [81826, 84564, 87686, 78379, 85333],   # 对照
        1: [82724, 84925, 88149, 78962, 85457],   # 实验1
        # 2: [...],  # 实验2（如有）
    }

    # 指标数据 — 按需填入
    metrics = {
        'AI渗透率': {
            'unit': '%',
            'category': '体验',
            'data': {
                0: [0.1956, 0.1915, 0.1820, 0.1897, 0.1930],
                1: [0.1924, 0.1920, 0.1849, 0.1919, 0.1972],
            },
            'multiply': 100,  # 显示时乘以100变百分比
        },
        '权益包人均消费': {
            'unit': '分',
            'category': '权益包',
            'data': {
                0: [29.55, 32.57, 30.69, 29.69, 30.21],
                1: [20.00, 37.75, 32.70, 75.75, 43.65],
            },
        },
        # 更多指标...
    }

    # ============================================================
    # 2. 分析
    # ============================================================

    control = 0
    experiment_groups = sorted([g for g in active_users.keys() if g != control])

    print("=" * 70)
    print(f"  实验分析（稳定期 {dates[0]}-{dates[-1]}）")
    print("=" * 70)

    # 流量分配
    print(f"\n📊 流量分配（末日活跃）")
    for g in [control] + experiment_groups:
        print(f"  组{g}: {active_users[g][-1]:,}")

    # 逐指标分析
    all_results = {}
    for name, cfg in metrics.items():
        data = cfg['data']
        mult = cfg.get('multiply', 1)
        unit = cfg.get('unit', '')
        cat = cfg.get('category', '')

        print(f"\n📊 {name} ({cat})")

        ctrl = data[control]
        ctrl_mean = np.mean(ctrl) * mult

        for g in experiment_groups:
            exp = data[g]
            exp_mean = np.mean(exp) * mult
            diff = exp_mean - ctrl_mean
            diff_pct = diff / ctrl_mean * 100 if ctrl_mean != 0 else 0
            t, p = stats.ttest_ind(ctrl, exp)
            sig = '✅' if p < 0.05 else '❌'

            print(f"  对照: {ctrl_mean:.2f}{unit}  组{g}: {exp_mean:.2f}{unit}  "
                  f"diff={diff:+.2f}({diff_pct:+.1f}%)  p={p:.4f} {sig}")

            all_results[(name, g)] = {
                'ctrl': ctrl_mean, 'exp': exp_mean,
                'diff': diff, 'pct': diff_pct, 'p': p
            }

    # ============================================================
    # 3. 异常值检测
    # ============================================================
    print(f"\n{'='*70}")
    print("  异常值检测（IQR法）")
    print("=" * 70)

    for name, cfg in metrics.items():
        data = cfg['data']
        all_vals = []
        for vals in data.values():
            all_vals.extend(vals)

        q1, q3 = np.percentile(all_vals, 25), np.percentile(all_vals, 75)
        iqr = q3 - q1
        lower, upper = q1 - 1.5 * iqr, q3 + 1.5 * iqr

        outliers = []
        for g, vals in data.items():
            for i, v in enumerate(vals):
                if v < lower or v > upper:
                    outliers.append(f"组{g} {dates[i]}: {v}")

        if outliers:
            print(f"\n  ⚡ {name}: 范围[{lower:.2f}, {upper:.2f}]")
            for o in outliers:
                print(f"    {o}")
        else:
            print(f"  ✅ {name}: 无异常值")

    # ============================================================
    # 4. 汇总表
    # ============================================================
    print(f"\n{'='*70}")
    print("  📋 汇总表")
    print("=" * 70)

    header = f"  {'指标':<20} {'对照':>10}"
    for g in experiment_groups:
        header += f"  {'组'+str(g):>15}"
    print(header)
    print("  " + "-" * (22 + 17 * len(experiment_groups)))

    for name, cfg in metrics.items():
        key = (name, experiment_groups[0])
        if key in all_results:
            r0 = all_results[key]
            line = f"  {name:<20} {r0['ctrl']:>10.2f}"
            for g in experiment_groups:
                r = all_results.get((name, g))
                if r:
                    sig = '✅' if r['p'] < 0.05 else '❌'
                    line += f"  {r['pct']:>+8.1f}% {sig}"
                else:
                    line += f"  {'—':>15}"
            print(line)


if __name__ == "__main__":
    analyze_experiment()

#!/usr/bin/env python3
"""
AB实验数据分析工具
用法: python3 ab_analysis.py <data_dir> [--stable-start YYYY-MM-DD] [--stable-end YYYY-MM-DD] [--control 0]
"""

import os
import sys
import json
import argparse
import zipfile
from datetime import datetime, date
from pathlib import Path

try:
    import openpyxl
except ImportError:
    print("需要安装 openpyxl: pip install openpyxl")
    sys.exit(1)

try:
    import numpy as np
    from scipy import stats
except ImportError:
    print("需要安装 scipy/numpy: pip install scipy numpy")
    sys.exit(1)


def read_xlsx(filepath):
    """读取xlsx文件，返回 (headers, rows)"""
    wb = openpyxl.load_workbook(filepath)
    ws = wb.active
    rows = []
    headers = None
    for i, row in enumerate(ws.iter_rows(values_only=True)):
        if i == 0:
            headers = row
        else:
            rows.append(row)
    return headers, rows


def extract_zips(data_dir, output_dir):
    """解压目录下所有zip文件"""
    zip_files = list(Path(data_dir).glob("*.zip"))
    extracted = []
    for i, zf in enumerate(zip_files):
        extract_to = os.path.join(output_dir, f"zip_{i+1}")
        os.makedirs(extract_to, exist_ok=True)
        with zipfile.ZipFile(zf) as z:
            z.extractall(extract_to)
        extracted.append(extract_to)
    return extracted


def parse_groups(headers):
    """从列名中解析分组编号"""
    groups = []
    for h in headers[1:]:  # 跳过日期列
        if h is None:
            continue
        h_str = str(h)
        # 尝试提取分组号: "分组（-1）", "试验组: -1", "-1" 等
        for pattern in ['-1', '0', '1', '2', '3', '4', '5']:
            if pattern in h_str:
                groups.append(int(pattern))
                break
    return groups


def detect_outliers_iqr(data_dict, dates):
    """
    IQR法检测异常值
    data_dict: {group_id: [values]}
    返回: 异常日期索引列表, 异常详情
    """
    all_values = []
    for vals in data_dict.values():
        all_values.extend(vals)

    q1 = np.percentile(all_values, 25)
    q3 = np.percentile(all_values, 75)
    iqr = q3 - q1
    lower = q1 - 1.5 * iqr
    upper = q3 + 1.5 * iqr

    outlier_indices = set()
    outlier_details = []

    for group, vals in data_dict.items():
        for i, v in enumerate(vals):
            if v < lower or v > upper:
                outlier_indices.add(i)
                outlier_details.append({
                    'group': group,
                    'date_idx': i,
                    'date': str(dates[i]) if i < len(dates) else f'idx_{i}',
                    'value': v,
                    'bound': 'upper' if v > upper else 'lower',
                    'threshold': upper if v > upper else lower
                })

    return sorted(outlier_indices), outlier_details, (lower, upper)


def run_ttest(control_data, experiment_data):
    """
    独立样本t检验
    返回: t_stat, p_value, significant(bool)
    """
    if len(control_data) < 2 or len(experiment_data) < 2:
        return None, None, False

    t_stat, p_value = stats.ttest_ind(control_data, experiment_data)
    return t_stat, p_value, p_value < 0.05


def calculate_arpu(revenue, active_users, scale=10000):
    """计算ARPU（万人均）"""
    return [r / a * scale for r, a in zip(revenue, active_users)]


def direction_arrow(diff_pct):
    """根据差异百分比返回方向箭头"""
    if abs(diff_pct) < 1:
        return "→"
    elif diff_pct > 0:
        return "↗"
    else:
        return "↘"


def format_significance(p_value):
    """格式化显著性标记"""
    if p_value is None:
        return "—"
    if p_value < 0.01:
        return f"p={p_value:.4f} ✅✅"
    elif p_value < 0.05:
        return f"p={p_value:.4f} ✅"
    else:
        return f"p={p_value:.4f} ❌"


def analyze_metric(name, data_dict, control_group=0, dates=None, unit=""):
    """
    分析单个指标
    data_dict: {group_id: [daily_values]}
    返回分析结果字典
    """
    results = {}
    control_data = data_dict.get(control_group, [])

    if not control_data:
        return {"error": f"对照组 {control_group} 无数据"}

    control_mean = np.mean(control_data)
    results['control'] = {
        'mean': control_mean,
        'std': np.std(control_data),
        'n': len(control_data)
    }

    results['experiments'] = {}
    for group, values in data_dict.items():
        if group == control_group or group == -1:
            continue

        exp_mean = np.mean(values)
        diff = exp_mean - control_mean
        diff_pct = diff / control_mean * 100 if control_mean != 0 else 0

        t_stat, p_value, significant = run_ttest(control_data, values)

        results['experiments'][group] = {
            'mean': exp_mean,
            'diff': diff,
            'diff_pct': diff_pct,
            'direction': direction_arrow(diff_pct),
            't_stat': t_stat,
            'p_value': p_value,
            'significant': significant,
        }

    # 异常值检测
    if dates:
        outlier_idx, outlier_details, bounds = detect_outliers_iqr(
            {k: v for k, v in data_dict.items() if k != -1},
            dates
        )
        results['outliers'] = {
            'indices': outlier_idx,
            'details': outlier_details,
            'bounds': bounds
        }

        # 去异常值后重算
        if outlier_idx:
            clean_indices = [i for i in range(len(control_data)) if i not in outlier_idx]
            if len(clean_indices) >= 2:
                clean_data = {
                    g: [v[i] for i in clean_indices]
                    for g, v in data_dict.items() if g != -1
                }
                results['clean'] = {}
                clean_control = clean_data[control_group]
                clean_control_mean = np.mean(clean_control)

                for group, values in clean_data.items():
                    if group == control_group:
                        continue
                    cm = np.mean(values)
                    cd = cm - clean_control_mean
                    cpct = cd / clean_control_mean * 100 if clean_control_mean != 0 else 0
                    ct, cp, cs = run_ttest(clean_control, values)
                    results['clean'][group] = {
                        'mean': cm,
                        'diff': cd,
                        'diff_pct': cpct,
                        'p_value': cp,
                        'significant': cs,
                    }

    return results


def print_summary_table(metrics_results, groups, control_group=0):
    """打印汇总表"""
    exp_groups = sorted([g for g in groups if g != control_group and g != -1])

    print(f"\n{'='*70}")
    print(f"  综合汇总（对照组{control_group} vs 实验组{'/'.join(map(str, exp_groups))}）")
    print(f"{'='*70}")

    header = f"  {'指标':<20} {'对照':>10}"
    for g in exp_groups:
        header += f"  {'组'+str(g):>12}"
    print(header)
    print("  " + "-" * (20 + 12 + 14 * len(exp_groups)))

    for name, result in metrics_results.items():
        if 'error' in result:
            continue

        ctrl_mean = result['control']['mean']
        line = f"  {name:<20} {ctrl_mean:>10.2f}"

        for g in exp_groups:
            if g in result.get('experiments', {}):
                exp = result['experiments'][g]
                diff_str = f"{exp['diff_pct']:+.1f}%"
                sig = "✅" if exp['significant'] else "❌"
                line += f"  {diff_str:>8} {sig}"
            else:
                line += f"  {'—':>12}"

        print(line)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="AB实验数据分析")
    parser.add_argument("data_dir", help="数据目录路径")
    parser.add_argument("--stable-start", help="稳定期开始日期 (YYYY-MM-DD)")
    parser.add_argument("--stable-end", help="稳定期结束日期 (YYYY-MM-DD)")
    parser.add_argument("--control", type=int, default=0, help="对照组编号 (默认0)")
    parser.add_argument("--scan", action="store_true", help="仅扫描文件结构，不分析")

    args = parser.parse_args()

    if args.scan:
        print(f"扫描目录: {args.data_dir}")
        for root, dirs, files in os.walk(args.data_dir):
            for f in sorted(files):
                if f.endswith('.xlsx'):
                    filepath = os.path.join(root, f)
                    headers, rows = read_xlsx(filepath)
                    print(f"\n  {os.path.relpath(filepath, args.data_dir)}")
                    print(f"    行数: {len(rows)}, 列数: {len(headers)}")
                    print(f"    列名: {headers}")
                    if rows:
                        print(f"    首行: {rows[0]}")
                        print(f"    末行: {rows[-1]}")
    else:
        print("请使用 --scan 先扫描数据结构，然后在代码中调用分析函数。")
        print("完整分析流程请参考 SKILL.md")

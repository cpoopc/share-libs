#!/usr/bin/env python3
"""Grafana CLI - 简化的 Grafana 数据查询工具

用法:
    # 列出 panels (包含查询语句)
    grafana-query panels <dashboard_uid> [--pattern <regex>] [--queries]
    
    # 通过 panel ID 获取数据
    grafana-query data <dashboard_uid> --panel <id> [--from now-7d] [--to now]
    
    # 通过 panel 名称匹配获取数据
    grafana-query data <dashboard_uid> --match "HTTP.*Success" [--from now-7d] [--to now]
    
    # 直接执行 PromQL 查询
    grafana-query query <expr> [--from now-7d] [--to now]
"""

import argparse
import json
import sys

from .client import GrafanaClient


def _output_data(data, title, agg="avg"):
    """输出数据，支持聚合"""
    if not data:
        print(f"{title}: N/A")
        return

    # 按 metric 分组
    by_metric = {}
    for row in data:
        metric = row.get("metric", "") or title
        value = row.get("value")
        if value is not None:
            if metric not in by_metric:
                by_metric[metric] = []
            by_metric[metric].append(value)

    # 输出聚合结果
    for metric, values in by_metric.items():
        if agg == "all":
            for v in values:
                print(f"{metric}: {v}")
        elif agg == "last":
            print(f"{metric}: {values[-1]}")
        elif agg == "min":
            print(f"{metric}: {min(values)}")
        elif agg == "max":
            print(f"{metric}: {max(values)}")
        else:  # avg (default)
            avg = sum(values) / len(values)
            print(f"{metric}: {avg:.2f}")


def cmd_panels(args):
    """列出 panels"""
    client = GrafanaClient.from_env(args.source)
    panels = client.list_panels(
        args.dashboard,
        pattern=args.pattern,
        include_queries=args.queries,
    )
    
    if args.json:
        print(json.dumps(panels, indent=2))
    else:
        for p in panels:
            print(f"[{p['id']:3d}] {p['title']}")
            if args.queries and p.get("queries"):
                for q in p["queries"]:
                    expr = q.get("expr") or q.get("query", "")
                    legend = q.get("legend", "")
                    print(f"      └─ {legend or q['refId']}: {expr[:80]}...")


def cmd_data(args):
    """获取 panel 数据"""
    client = GrafanaClient.from_env(args.source)

    # 查找 panel
    if args.panel:
        panel = client.find_panel(args.dashboard, panel_id=args.panel)
    elif args.match:
        panel = client.find_panel(args.dashboard, pattern=args.match)
    else:
        print("Error: --panel or --match required", file=sys.stderr)
        sys.exit(1)

    print(f"📈 {panel['title']} (ID: {panel['id']})", file=sys.stderr)

    # 获取数据
    data = client.get_panel_data(
        dashboard_uid=args.dashboard,
        panel_id=panel["id"],
        time_from=args.time_from,
        time_to=args.time_to,
    )

    # 输出
    if args.json:
        print(json.dumps(data, indent=2))
    else:
        _output_data(data, panel["title"], args.agg)


def cmd_query(args):
    """直接执行查询"""
    client = GrafanaClient.from_env(args.source)

    data = client.query_custom(
        expr=args.expr,
        time_from=args.time_from,
        time_to=args.time_to,
    )

    if args.json:
        print(json.dumps(data, indent=2))
    else:
        _output_data(data, "result", args.agg)


def main():
    parser = argparse.ArgumentParser(description="Grafana CLI")
    parser.add_argument("--source", "-s", default="", help="Grafana source ID (env: GRAFANA_<SOURCE>_*)")
    
    subparsers = parser.add_subparsers(dest="command", required=True)
    
    # panels 子命令
    p_panels = subparsers.add_parser("panels", help="List panels in a dashboard")
    p_panels.add_argument("dashboard", help="Dashboard UID")
    p_panels.add_argument("--pattern", "-p", help="Regex pattern to filter panels")
    p_panels.add_argument("--queries", "-q", action="store_true", help="Show query expressions")
    p_panels.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    p_panels.set_defaults(func=cmd_panels)
    
    # data 子命令
    p_data = subparsers.add_parser("data", help="Fetch panel data")
    p_data.add_argument("dashboard", help="Dashboard UID")
    p_data.add_argument("--panel", "-p", type=int, help="Panel ID")
    p_data.add_argument("--match", "-m", help="Regex pattern to match panel title")
    p_data.add_argument("--from", dest="time_from", default="now-7d", help="Start time")
    p_data.add_argument("--to", dest="time_to", default="now", help="End time")
    p_data.add_argument("--agg", "-a", choices=["avg", "last", "min", "max", "all"], default="avg",
                        help="Aggregation method (default: avg)")
    p_data.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    p_data.set_defaults(func=cmd_data)

    # query 子命令
    p_query = subparsers.add_parser("query", help="Execute PromQL query directly")
    p_query.add_argument("expr", help="PromQL expression")
    p_query.add_argument("--from", dest="time_from", default="now-7d", help="Start time")
    p_query.add_argument("--to", dest="time_to", default="now", help="End time")
    p_query.add_argument("--agg", "-a", choices=["avg", "last", "min", "max", "all"], default="avg",
                        help="Aggregation method (default: avg)")
    p_query.add_argument("--json", "-j", action="store_true", help="Output as JSON")
    p_query.set_defaults(func=cmd_query)
    
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()


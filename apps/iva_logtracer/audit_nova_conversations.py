#!/usr/bin/env python3
import os
import sys
import json
import re
import csv
import argparse
from datetime import datetime, timedelta, timezone
from typing import Set, Dict, List, Optional, NamedTuple
from collections import defaultdict
from pathlib import Path

# 添加工具库路径
sys.path.append(str(Path(__file__).parent.parent.parent / "tools" / "python" / "libs" / "kibana"))

from cptools_kibana.client import KibanaClient, KibanaConfig

class LogEntry(NamedTuple):
    timestamp: str
    message: str
    accountId: Optional[str]
    brandId: Optional[str]
    sessionId: Optional[str]
    conversationId: Optional[str]

def get_kibana_client(env_name: str = "production") -> KibanaClient:
    """获取 Kibana 客户端"""
    # 尝试加载 .env 文件
    # 优先加载指定环境的 .env 文件 (e.g. .env.lab, .env.production)
    # 如果找不到，回退到 .env
    
    env_files = [
        Path(__file__).parent / f".env.{env_name}",
        Path(__file__).parent / ".env"
    ]
    
    loaded = False
    for env_path in env_files:
        if env_path.exists():
            print(f"Loading env from {env_path}")
            with open(env_path) as f:
                for line in f:
                    if line.strip() and not line.startswith('#'):
                        try:
                            key, value = line.strip().split('=', 1)
                            # 去除可能的引号
                            value = value.strip().strip("'").strip('"')
                            if not os.getenv(key):
                                os.environ[key] = value
                        except ValueError:
                            continue
            loaded = True
            break
            
    if not loaded:
        print(f"WARNING: No .env file found for environment '{env_name}'")

    return KibanaClient.from_env()

def extract_field(message: str, field: str) -> Optional[str]:
    """从日志消息中提取字段 (accountId, brandId, etc)"""
    # 尝试解析 JSON
    try:
        data = json.loads(message)
        if isinstance(data, dict):
            if field in data:
                return str(data[field])
    except json.JSONDecodeError:
        pass

    # 尝试正则提取 JSON-like
    # 匹配 "field": 12345 或 "field": "12345"
    pattern = rf'"{field}"\s*:\s*"?([^",\}}]+)"?'
    match = re.search(pattern, message)
    if match:
        return match.group(1)
    
    return None

def fetch_logs(client: KibanaClient, query: str, time_range_hours: int, index: str) -> List[LogEntry]:
    """拉取日志 (Available to fetch all via Scroll API)"""
    print(f"Searching: {query} (Last {time_range_hours}h)...")
    
    end_time = datetime.now(timezone.utc)
    start_time = end_time - timedelta(hours=time_range_hours)
    
    # 格式化为 ES 时间字符串
    fmt = "%Y-%m-%dT%H:%M:%S.%fZ"
    start_str = start_time.strftime(fmt)
    end_str = end_time.strftime(fmt)

    # 构建基础查询 body
    body: Dict[str, Any] = {
        "query": {
            "bool": {
                "must": [],
                "filter": [],
            }
        },
        "size": 1000, # Page size for scroll
        "_source": {
             "includes": ["message", "accountId", "brandId", "sessionId", "conversationId", "@timestamp"]
        },
        "sort": [{"@timestamp": {"order": "desc"}}]
    }
    
    # 添加查询字符串
    if query and query.strip() and query != "*":
        body["query"]["bool"]["must"].append({
            "query_string": {
                "query": query,
                "analyze_wildcard": True,
            }
        })
    
    # 添加时间范围
    body["query"]["bool"]["filter"].append({
        "range": {
            "@timestamp": {
                "gte": start_str,
                "lte": end_str
            }
        }
    })

    all_logs = []
    
    try:
        # 1. Initiate Scroll
        # Note: client.search doesn't expose scroll param directly in signature, so we use _request
        # Method: POST {index}/_search?scroll=2m
        path = f"{index}/_search?scroll=2m"
        result = client._request("POST", path, body)
        
        scroll_id = result.get("_scroll_id")
        hits_data = result.get("hits", {})
        total = hits_data.get("total", {}).get("value", 0)
        hits = hits_data.get("hits", [])
        
        print(f"Found {total} logs. Fetching...")
        
        while hits:
            # Process current batch
            for hit in hits:
                source = hit.get("_source", {})
                msg = source.get("message", "")
                
                # 优先使用 ES 索引字段
                acc_id = source.get("accountId")
                brand_id = source.get("brandId")
                sess_id = source.get("sessionId")
                conv_id = source.get("conversationId")
                
                # 提取 accountId
                if not acc_id:
                    acc_id = extract_field(msg, "accountId")
                
                # 提取 brandId
                if not brand_id:
                    brand_id = extract_field(msg, "brandId")
        
                # 提取 sessionId
                if not sess_id:
                    sess_id = extract_field(msg, "sessionId")
                    
                # 提取 conversationId
                if not conv_id:
                    conv_id = extract_field(msg, "conversationId")
                    
                all_logs.append(LogEntry(
                    timestamp=source.get("@timestamp"),
                    message=msg,
                    accountId=str(acc_id) if acc_id else None,
                    brandId=str(brand_id) if brand_id else None,
                    sessionId=str(sess_id) if sess_id else None,
                    conversationId=str(conv_id) if conv_id else None
                ))
            
            print(f"Fetched {len(all_logs)} / {total} logs...", end="\r")
            
            if not scroll_id:
                break
                
            # 2. Continue Scroll
            # Method: POST /_search/scroll
            # Body: { "scroll": "2m", "scroll_id": ... }
            scroll_body = {
                "scroll": "2m",
                "scroll_id": scroll_id
            }
            
            # Note: _search/scroll endpoint is global, not index specific
            result = client._request("POST", "_search/scroll", scroll_body)
            scroll_id = result.get("_scroll_id") # Update scroll_id
            hits = result.get("hits", {}).get("hits", [])

        print(f"\nFetch complete. Total logs processed: {len(all_logs)}")
        
        # 3. Clear Scroll (Callback)
        if scroll_id:
            try:
                client._request("DELETE", "_search/scroll", {"scroll_id": [scroll_id]})
            except:
                pass

    except Exception as e:
        print(f"Error during search: {e}")
        # Return whatever we got so far
        return all_logs
        
    return all_logs

# Brand ID Mapping
BRAND_MAPPING = {
    "1210": "RingCentral",
    "1250": "RingCentral for Government",
    "2000": "Rise I",
    "2010": "RingCentral EU",
    "2020": "Unify Office (Atos)",
    "2030": "RingCentral mit Telecom (DT-RCO)",
    "2040": "Unify Office by RingCentral",
    "2050": "RingCentral with Sunrise",
    "2210": "RingCentral with Verizon",
    "3000": "Rise A",
    "3460": "AT&T Office@Hand",
    "3610": "RingCentral Canada",
    "3710": "RingCentral UK",
    "4210": "RingCentral mit ecotel",
    "4610": "RingCentral with Eastlink",
    "4710": "1&1 Connected Calls (Versatel)",
    "4810": "RingCentral for Symphony (MCM)",
    "4910": "Frontier plus RingCentral",
    "5010": "RingCentral AU",
    "5110": "CharterSMB with RingCentral",
    "5210": "CharterENT with RingCentral",
    "6010": "Avaya Cloud Office",
    "7010": "Vodafone",
    "7310": "TELUS",
    "7710": "BT Business"
}

def main():
    parser = argparse.ArgumentParser(description="Audit Nova Conversation Creation")
    parser.add_argument("--hours", type=int, default=24, help="Time range in hours")
    parser.add_argument("--exclude-brand", type=str, default="1210", help="Brand IDs to exclude (comma-separated, e.g. '1210,3610')")
    parser.add_argument("--index", type=str, default="*:*-logs-air_assistant_runtime-*", help="Index pattern")
    parser.add_argument("--output", type=str, default="output/audit_report.csv", help="Output CSV path")
    parser.add_argument("--target-ids", nargs="+", help="Specific IDs to trace (accountId, sessionId, etc.)")
    parser.add_argument("--env", type=str, default="production", help="Environment config to load (e.g. production, lab)")
    
    args = parser.parse_args()
    
    client = get_kibana_client(args.env)
    
    # Parse excluded brands
    excluded_brands = [b.strip() for b in args.exclude_brand.split(",") if b.strip()]
    
    results = []
    
    if args.target_ids:
        print(f"Target Mode: Tracing {len(args.target_ids)} IDs...")
        
        # In Target Mode, we search for ANY log containing the ID
        # Then reconstruct the state from the traces
        ids_query = " OR ".join([f'"{tid}"' for tid in args.target_ids])
        query = f"({ids_query})"
        
        logs = fetch_logs(client, query, args.hours, args.index)
        
        # Group by accountId (if available) or create entries for each target ID if we can't link them
        # Better: Group by "Primary ID" which is one of the target IDs or the accountId found/associated
        # Since we want to output rows like the standard report, we ideally want to group by Account ID.
        # But if the user provides a session ID and we never find the account ID, we should still report it.
        
        traces = defaultdict(lambda: {
            "accountId": None, "brandId": "Unknown", "sessionId": None, "conversationId": None,
            "startTime": None, "status": "Unknown", "flowType": "Unknown", "signal": "No Signal",
            "logs": []
        })
        
        for log in logs:
            key = log.accountId
            
            # If we lack accountId, try to use sessionId or convertationId if they match a target
            if not key:
                if log.sessionId and log.sessionId in args.target_ids:
                    key = log.sessionId # Temporary key
                elif log.conversationId and log.conversationId in args.target_ids:
                    key = log.conversationId
                else:
                    # Fallback: check if message contains any target ID
                    for tid in args.target_ids:
                        if tid in log.message:
                            key = tid
                            break
            
            if not key:
                continue

            # Update trace info
            t = traces[key]
            t["logs"].append(log)
            
            if log.accountId: t["accountId"] = log.accountId
            if log.brandId: t["brandId"] = log.brandId
            if log.sessionId: t["sessionId"] = log.sessionId
            if log.conversationId: t["conversationId"] = log.conversationId
            
            # Check for Start Signal
            if "Start processing task" in log.message:
                if t["startTime"] is None or log.timestamp < t["startTime"]:
                    t["startTime"] = log.timestamp
            
            # Check for Success/Fail Signals
            if "Nova Conversation is created" in log.message:
                t["status"] = "Success"
                t["flowType"] = "Nova"
                t["signal"] = "Nova Created"
            elif "Created new Conversation" in log.message:
                if t["flowType"] != "Nova": # Don't overwrite Nova
                    t["status"] = "Success"
                    t["flowType"] = "Classic"
                    t["signal"] = "Session Created"
            elif "Failed to create Nova conversation" in log.message:
                 t["status"] = "Fail"
                 t["flowType"] = "Nova"
                 t["signal"] = "Explicit Nova Fail"
                 
        for key, t in traces.items():
            if not t["startTime"] and t["logs"]:
                t["logs"].sort(key=lambda x: x.timestamp)
                t["startTime"] = t["logs"][0].timestamp
                
            if t["status"] == "Unknown":
                 t["status"] = "Fail"
                 t["signal"] = "No Success Signal Found"

            results.append({
                "accountId": t["accountId"] or key,
                "brandId": t["brandId"],
                "brandName": BRAND_MAPPING.get(t["brandId"], "Unknown"),
                "sessionId": t["sessionId"],
                "conversationId": t["conversationId"],
                "status": t["status"],
                "flowType": t["flowType"],
                "startTime": t["startTime"],
                "signal": t["signal"]
            })
            
    else:
        # Standard Audit Mode
        exclude_query = " AND ".join([f'NOT message:"\\"brandId\\":\\"{b}\\""' for b in excluded_brands])
        if not exclude_query:
            start_query = 'message:"Start processing task"'
        else:
            start_query = f'message:"Start processing task" AND {exclude_query}'
            
        start_logs = fetch_logs(client, start_query, args.hours, args.index)
        
        started_accounts: Dict[str, Dict] = {}
        
        for log in start_logs:
            if log.accountId:
                if log.accountId not in started_accounts:
                    started_accounts[log.accountId] = {
                        "startTime": log.timestamp,
                        "brandId": log.brandId or "Unknown",
                        "sessionId": log.sessionId or ""
                    }

        print(f"Found {len(started_accounts)} unique accounts started processing.")
        
        if not started_accounts:
            print("No accounts found. Exiting.")
            return

        candidate_ids = list(started_accounts.keys())
        chunk_size = 50
        
        nova_success_set: Set[str] = set()
        any_success_set: Set[str] = set()
        success_info: Dict[str, Dict] = {} # accountId -> {signal, conversationId}

        for i in range(0, len(candidate_ids), chunk_size):
            chunk = candidate_ids[i:i + chunk_size]
            ids_query = " OR ".join([f'"{cid}"' for cid in chunk])
            
            success_query = f'(message:"Nova Conversation is created" OR message:"Created new Conversation") AND ({ids_query})'
            
            chunk_logs = fetch_logs(client, success_query, args.hours, args.index)
            
            for log in chunk_logs:
                if log.accountId:
                    any_success_set.add(log.accountId)
                    
                    signal_type = "Unknown"
                    if "Nova Conversation is created" in log.message:
                        nova_success_set.add(log.accountId)
                        signal_type = "Nova Created"
                    elif "Created new Conversation" in log.message:
                        signal_type = "Session Created"
                    else:
                        signal_type = "Other Success"
                        
                    if log.accountId not in success_info or signal_type == "Nova Created":
                        success_info[log.accountId] = {
                            "signal": signal_type,
                            "conversationId": log.conversationId or ""
                        }

        print(f"Found {len(any_success_set)} unique accounts with success signal ({len(nova_success_set)} Nova).")

        fail_query = 'message:"Failed to create Nova conversation"'
        fail_logs = fetch_logs(client, fail_query, args.hours, args.index)
        
        nova_fail_set: Set[str] = set()
        for log in fail_logs:
            if log.accountId:
                nova_fail_set.add(log.accountId)
                
        for acc_id, data in started_accounts.items():
            brand_id = data["brandId"]
            start_time = data["startTime"]
            session_id = data["sessionId"]
            
            status = "Unknown"
            flow_type = "Unknown"
            signal = ""
            conversation_id = ""
            
            if acc_id in success_info:
                info = success_info[acc_id]
                conversation_id = info["conversationId"]
                
            if acc_id in nova_success_set:
                status = "Success"
                flow_type = "Nova"
                signal = success_info.get(acc_id, {}).get("signal", "Nova Created")
            elif acc_id in any_success_set:
                status = "Success"
                flow_type = "Classic" 
                signal = success_info.get(acc_id, {}).get("signal", "Session Created")
            elif acc_id in nova_fail_set:
                status = "Fail"
                flow_type = "Nova"
                signal = "Explicit Nova Fail Log"
            else:
                status = "Fail"
                flow_type = "Unknown"
                signal = "No Success Signal"
                
            results.append({
                "accountId": acc_id,
                "brandId": brand_id,
                "brandName": BRAND_MAPPING.get(brand_id, "Unknown"),
                "sessionId": session_id,
                "conversationId": conversation_id,
                "status": status,
                "flowType": flow_type,
                "startTime": start_time,
                "signal": signal
            })
            
    # --- Output ---
    # Calculate Stats
    brand_stats = defaultdict(lambda: {
        "total": 0, 
        "nova_success": 0, "classic_success": 0, 
        "nova_fail": 0, "unknown_fail": 0,
        "name": "Unknown"
    })
    
    for r in results:
        bid = r["brandId"]
        brand_stats[bid]["total"] += 1
        brand_stats[bid]["name"] = r["brandName"]
        
        if r["flowType"] == "Nova" and r["status"] == "Success":
            brand_stats[bid]["nova_success"] += 1
        elif r["flowType"] == "Classic" and r["status"] == "Success":
            brand_stats[bid]["classic_success"] += 1
        elif r["flowType"] == "Nova" and r["status"] == "Fail":
             brand_stats[bid]["nova_fail"] += 1
        else:
             brand_stats[bid]["unknown_fail"] += 1

    # 1. Print Stats Table
    print("\n" + "="*115)
    print(f"{'Brand ID':<12} | {'Brand Name':<30} | {'Total':<6} | {'NovaSucc':<8} | {'ClsSucc':<8} | {'NovaFail':<8} | {'UnkFail':<8} | {'NovaRate':<8}")
    print("-" * 115)
    
    sorted_brands = sorted(brand_stats.items(), key=lambda x: x[1]['total'], reverse=True)
    
    for brand_id, stats in sorted_brands:
        name = stats['name']
        # Truncate long names for display
        if len(name) > 30: name = name[:27] + "..."
            
        total = stats['total']
        n_succ = stats['nova_success']
        c_succ = stats['classic_success']
        n_fail = stats['nova_fail']
        u_fail = stats['unknown_fail']
        
        nova_attempts = n_succ + n_fail
        # NovaRate = (NovaSucc + NovaFail) / Total (Adoption Rate)
        nova_rate = (nova_attempts / total * 100) if total > 0 else 0.0
        
        print(f"{brand_id:<12} | {name:<30} | {total:<6} | {n_succ:<8} | {c_succ:<8} | {n_fail:<8} | {u_fail:<8} | {nova_rate:.1f}%")
    print("="*115 + "\n")
    
    # 2. Save CSV
    output_path = Path(args.output)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    
    with open(output_path, 'w', newline='') as f:
        fieldnames = ["accountId", "brandId", "brandName", "sessionId", "conversationId", "status", "flowType", "startTime", "signal"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(results)
        
    print(f"Detailed report saved to {output_path}")

    # 3. Save Stats CSV
    stats_path = output_path.with_name(f"{output_path.stem}_stats{output_path.suffix}")
    
    with open(stats_path, 'w', newline='') as f:
        fieldnames = ["BrandID", "BrandName", "Total", "NovaSucc", "ClsSucc", "NovaFail", "UnkFail", "NovaRate"]
        writer = csv.DictWriter(f, fieldnames=fieldnames)
        writer.writeheader()
        
        for brand_id, stats in sorted_brands:
            total = stats['total']
            n_succ = stats['nova_success']
            c_succ = stats['classic_success']
            n_fail = stats['nova_fail']
            u_fail = stats['unknown_fail']
            
            nova_attempts = n_succ + n_fail
            # NovaRate = (NovaSucc + NovaFail) / Total (Adoption Rate)
            nova_rate = (nova_attempts / total) if total > 0 else 0.0
            
            writer.writerow({
                "BrandID": brand_id,
                "BrandName": stats['name'],
                "Total": total,
                "NovaSucc": n_succ,
                "ClsSucc": c_succ,
                "NovaFail": n_fail,
                "UnkFail": u_fail,
                "NovaRate": f"{nova_rate:.1%}"
            })
            
    print(f"Statistics report saved to {stats_path}")

if __name__ == "__main__":
    main()

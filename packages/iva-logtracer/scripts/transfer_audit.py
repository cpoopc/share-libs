#!/usr/bin/env python3
"""
Transfer Audit - 只下载关键字段，筛选发生 transfer 的会话，提取：
- 用户原话 (user transcript)
- 转接目标 (transfer to extensionId / number)
- 该会话/账号的 backup extension 配置

Backup 来源（代码对应）：
- agent_service 中 logger.info("prepare build context %o", logForBuildContext)，
  logForBuildContext = { fallbackExtension, disableTransferByContext, normalizedRoutingRules, ... }
  即 fallbackExtension 在 "prepare build context" 这条日志的打印对象里。
- 搜索 agent_service 时可用 conversationId 或 assistantId 匹配；按 assistantId 可命中该 assistant 的 prepare build context 日志。

用法（需先 source .env.production）:
  cd apps/iva_logtracer && uv run python scripts/transfer_audit.py 37439510 --last 7d --size 5000
或通过 runner:
  ./apps/iva_logtracer/runners/run_transfer_audit.sh 37439510 --env production --last 7d
"""

import argparse
import json
import re
import sys
from collections import defaultdict
from pathlib import Path

# 支持从项目根或 iva_logtracer 运行
from logtracer_extractors.runtime import get_app_root

ROOT = get_app_root()
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from logtracer_extractors.kibana_client import KibanaClient, parse_time_range

ASSISTANT_RUNTIME_INDEX = "*:*-logs-air_assistant_runtime-*"
AGENT_SERVICE_INDEX = "*:*-logs-air_agent_service-*"
SOURCE_INCLUDES = ["@timestamp", "message", "conversationId", "sessionId", "accountId"]
AGENT_SERVICE_SOURCE_INCLUDES = ["@timestamp", "message", "conversationId", "assistantId"]


def fetch_logs(client: KibanaClient, account_id: str, last: str, size: int):
    """只拉取关键字段的 assistant_runtime 日志."""
    start_time = parse_time_range(last)
    return client.search(
        query=f'accountId:"{account_id}"',
        index=ASSISTANT_RUNTIME_INDEX,
        start_time=start_time,
        end_time="now",
        size=size,
        source_includes=SOURCE_INCLUDES,
    )


def fetch_agent_service_logs(client: KibanaClient, conversation_ids: list[str], last: str, size_per_cid: int = 300):
    """按 conversationId 拉取 agent_service 日志（用于从 prepare build context 取 fallbackExtension）。"""
    if not conversation_ids:
        return []
    ids_clause = " OR ".join(f'"{cid}"' for cid in conversation_ids)
    query = f"conversationId:({ids_clause})"
    start_time = parse_time_range(last)
    total_size = min(size_per_cid * len(conversation_ids), 5000)
    result = client.search(
        query=query,
        index=AGENT_SERVICE_INDEX,
        start_time=start_time,
        end_time="now",
        size=total_size,
        source_includes=AGENT_SERVICE_SOURCE_INCLUDES,
    )
    hits = result.get("hits", {}).get("hits", [])
    return [h.get("_source", {}) for h in hits]


def fetch_agent_service_logs_by_assistant_id(client: KibanaClient, assistant_ids: list[str], last: str, size: int = 500):
    """按 assistantId 拉取 agent_service 日志（匹配 prepare build context，含 fallbackExtension）。"""
    if not assistant_ids:
        return []
    aids_clause = " OR ".join(f'"{aid}"' for aid in assistant_ids)
    # 可选：message 含 prepare build context 减少噪音
    query = f'assistantId:({aids_clause}) AND message:"prepare build context"'
    start_time = parse_time_range(last)
    result = client.search(
        query=query,
        index=AGENT_SERVICE_INDEX,
        start_time=start_time,
        end_time="now",
        size=size,
        source_includes=AGENT_SERVICE_SOURCE_INCLUDES,
    )
    hits = result.get("hits", {}).get("hits", [])
    return [h.get("_source", {}) for h in hits]


def extract_conversation_id(log: dict) -> str | None:
    return log.get("conversationId")


def is_transfer_conversation(messages: list[dict]) -> bool:
    for log in messages:
        msg = (log.get("message") or "").strip()
        if "Forwarding call to" in msg or "forward: OK" in msg or "CallForwarded" in msg:
            return True
    return False


def extract_forward_to(message: str) -> dict | None:
    """从 forward: OK, body: {...} 提取 to.extensionId / to.extensionNumber / to.phoneNumber."""
    if "forward: OK" not in message or "body:" not in message:
        return None
    # 从 body: 后开始找 "to":{ ... }（可能含嵌套，取到匹配的 }）
    idx = message.find("body:")
    if idx == -1:
        return None
    rest = message[idx:]
    to_start = rest.find('"to":')
    if to_start == -1:
        return None
    rest = rest[to_start:]
    brace = rest.find("{")
    if brace == -1:
        return None
    depth = 0
    end = -1
    for i, c in enumerate(rest[brace:], start=brace):
        if c == "{":
            depth += 1
        elif c == "}":
            depth -= 1
            if depth == 0:
                end = i
                break
    if end == -1:
        return None
    to_block = rest[brace : end + 1]
    ext_id = re.search(r'"extensionId"\s*:\s*["\']?([^",}\s]+)["\']?', to_block)
    ext_num = re.search(r'"extensionNumber"\s*:\s*"([^"]+)"', to_block)
    phone = re.search(r'"phoneNumber"\s*:\s*"([^"]+)"', to_block)
    name = re.search(r'"name"\s*:\s*"([^"]+)"', to_block)
    return {
        "extensionId": ext_id.group(1) if ext_id else None,
        "extensionNumber": ext_num.group(1) if ext_num else None,
        "phoneNumber": phone.group(1) if phone else None,
        "name": name.group(1) if name else None,
    }


def extract_user_transcripts(messages: list[dict]) -> list[str]:
    """从 Received transcript 或 human content 提取用户原话."""
    user_words: list[str] = []
    seen = set()
    for log in messages:
        msg = (log.get("message") or "").strip()
        # Received transcript: [Yes.], sseq: 7, isFinal: true
        m = re.search(r'Received transcript:\s*\[([^\]]*)\]', msg)
        if m:
            text = m.group(1).strip()
            if text and text not in seen:
                user_words.append(text)
                seen.add(text)
        # "content":{"oneofKind":"human","human":{"content":"porting"}}
        m = re.search(r'"human"\s*:\s*\{[^}]*"content"\s*:\s*"([^"]*)"', msg)
        if m:
            text = m.group(1).strip()
            if text and text not in seen:
                user_words.append(text)
                seen.add(text)
        # generate messages with "human" content
        m = re.search(r'"content"\s*:\s*"([^"]+)"[^}]*"human"', msg)
        if m:
            text = m.group(1).strip()
            if text and len(text) < 500 and text not in seen:
                user_words.append(text)
                seen.add(text)
    return user_words


def extract_fallback_extension(messages: list[dict]) -> str | None:
    """从 assistant_runtime：Start processing task 的 fallbackExtensionNumber 或 assistantInfo 的 fallbackExtension."""
    for log in messages:
        msg = (log.get("message") or "").strip()
        # "fallbackExtensionNumber":"101"
        m = re.search(r'"fallbackExtensionNumber"\s*:\s*"([^"]*)"', msg)
        if m:
            return m.group(1) or None
        # "fallbackExtension":"101"
        m = re.search(r'"fallbackExtension"\s*:\s*"([^"]*)"', msg)
        if m and m.group(1):
            return m.group(1)
    return None


def extract_fallback_from_agent_service(messages: list[dict]) -> str | None:
    """从 agent_service 的 prepare build context 提取 fallbackExtension，如 \"fallbackExtension\":\"\\\"20269\\\"\" 或 \"101\"."""
    for log in messages:
        msg = (log.get("message") or "").strip()
        if "prepare build context" not in msg or "fallbackExtension" not in msg:
            continue
        m = re.search(r'"fallbackExtension"\s*:\s*"((?:[^"\\]|\\.)*)"', msg)
        if m:
            val = m.group(1).replace('\\"', "").strip('"')
            return val or None
    return None


def extract_transfer_by_context_from_message(msg: str) -> dict | None:
    """从 prepare build context 单条 message 提取 disableTransferByContext 与 normalizedRoutingRules（transfer by context 规则）. 与 logForBuildContext 对应."""
    if "prepare build context" not in msg:
        return None
    out: dict = {}
    # "disableTransferByContext":true 或 false
    m = re.search(r'"disableTransferByContext"\s*:\s*(true|false)', msg, re.IGNORECASE)
    if m:
        out["disableTransferByContext"] = m.group(1).lower() == "true"
    # "normalizedRoutingRules":"  - \"20280\" : \"...\"\n  - \"20263\" : \"...\"  （可能很长，含 \n \", 取到下一个 key 前）
    m = re.search(r'"normalizedRoutingRules"\s*:\s*"((?:[^"\\]|\\.)*)"', msg)
    if m:
        raw = m.group(1).replace('\\n', "\n").replace('\\"', '"')
        out["normalizedRoutingRules"] = raw.strip()
    return out if out else None


def extract_from_fallback_flag(messages: list[dict]) -> bool | None:
    """本次转接是否来自 backup (from_fallback_extension: true/false)."""
    for log in messages:
        msg = (log.get("message") or "").strip()
        if "from_fallback_extension" not in msg:
            continue
        if "from_fallback_extension\":true" in msg or '"from_fallback_extension": true' in msg:
            return True
        if "from_fallback_extension\":false" in msg or '"from_fallback_extension": false' in msg:
            return False
    return None


def extract_transfer_extension_number_from_tool(message: str) -> str | None:
    """从 transfer_call 的 input 里取 number (extension number 请求)."""
    m = re.search(r'"number"\s*:\s*"([^"]+)"', message)
    return m.group(1) if m else None


def extract_assistant_id_from_messages(messages: list[dict]) -> str | None:
    """从 assistant_runtime 的 context 里提取 assistantId（如 \"assistantId\":\"d8b73457-da6c-4226-bbbd-967401337921\"）."""
    uuid_re = r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}"
    for log in messages:
        msg = (log.get("message") or "").strip()
        m = re.search(r'"assistantId"\s*:\s*"(' + uuid_re + r')"', msg)
        if m:
            return m.group(1)
    return None


def build_fallback_by_assistant_id(agent_service_logs: list[dict]) -> dict[str, str]:
    """从 agent_service 日志（含 prepare build context）构建 assistantId -> fallbackExtension."""
    out: dict[str, str] = {}
    for log in agent_service_logs:
        msg = (log.get("message") or "").strip()
        if "prepare build context" not in msg or "fallbackExtension" not in msg:
            continue
        aid = log.get("assistantId")
        if not aid:
            continue
        val = extract_fallback_from_agent_service([log])
        if val:
            out[aid] = val
    return out


def build_context_by_assistant_id(agent_service_logs: list[dict]) -> dict[str, dict]:
    """从 agent_service 的 prepare build context 构建 assistantId -> { fallbackExtension, disableTransferByContext, normalizedRoutingRules }."""
    out: dict[str, dict] = {}
    for log in agent_service_logs:
        msg = (log.get("message") or "").strip()
        ctx = extract_transfer_by_context_from_message(msg)
        if not ctx:
            continue
        aid = log.get("assistantId")
        if not aid:
            continue
        fallback = extract_fallback_from_agent_service([log])
        out[aid] = {
            "fallbackExtension": fallback,
            "disableTransferByContext": ctx.get("disableTransferByContext"),
            "normalizedRoutingRules": ctx.get("normalizedRoutingRules") or "",
        }
    return out


def rule_extension_matches(transfer_ext: str, normalized_routing_rules: str) -> list[str]:
    """检查 transfer 目标分机是否出现在 transfer-by-context 规则中，并返回匹配到的规则行（extension : intents）. 用于核对是否受该规则影响."""
    if not transfer_ext or not normalized_routing_rules:
        return []
    lines: list[str] = []
    for line in normalized_routing_rules.split("\n"):
        line = line.strip()
        # 格式如: - "20280" : "Credit Card Payment, ..." 或 "20225" : "..."
        if transfer_ext in line and (f'"{transfer_ext}"' in line or f"\"{transfer_ext}\"" in line):
            lines.append(line[:200] + ("..." if len(line) > 200 else ""))
    return lines


def build_audit(
    logs: list[dict],
    account_id: str,
    agent_service_by_cid: dict[str, list[dict]] | None = None,
    fallback_by_assistant_id: dict[str, str] | None = None,
    context_by_assistant_id: dict[str, dict] | None = None,
) -> list[dict]:
    """按 conversationId 分组，只保留有 transfer 的会话，并提取关键信息. 补全 backup；若提供 context_by_assistant_id 则附加 transfer-by-context 相关字段."""
    by_cid: dict[str, list[dict]] = defaultdict(list)
    for log in logs:
        cid = extract_conversation_id(log)
        if cid:
            by_cid[cid].append(log)
    for cid in by_cid:
        by_cid[cid].sort(key=lambda x: x.get("@timestamp") or "")

    result = []
    for conversation_id, messages in by_cid.items():
        if not is_transfer_conversation(messages):
            continue
        user_words = extract_user_transcripts(messages)
        backup = extract_fallback_extension(messages)
        if not backup and agent_service_by_cid:
            as_msgs = agent_service_by_cid.get(conversation_id, [])
            backup = extract_fallback_from_agent_service(as_msgs) or backup
        assistant_id = extract_assistant_id_from_messages(messages)
        if not backup and fallback_by_assistant_id and assistant_id:
            backup = fallback_by_assistant_id.get(assistant_id) or backup
        from_fallback = extract_from_fallback_flag(messages)
        transfer_to = None
        transfer_extension_number = None
        first_ts = None
        for log in messages:
            msg = (log.get("message") or "").strip()
            if not first_ts:
                first_ts = log.get("@timestamp")
            if "Forwarding call to" in msg or "forward: OK" in msg:
                t = extract_forward_to(msg)
                if t:
                    transfer_to = t
                if "extensionNumber" in msg:
                    m = re.search(r'"extensionNumber"\s*:\s*"([^"]+)"', msg)
                    if m:
                        transfer_extension_number = m.group(1)
            if "transfer_call" in msg and '"number"' in msg:
                n = extract_transfer_extension_number_from_tool(msg)
                if n:
                    transfer_extension_number = n

        ext_num = transfer_extension_number or (transfer_to.get("extensionNumber") if transfer_to else None)
        ctx = (context_by_assistant_id or {}).get(assistant_id or "") or {}
        rules_str = ctx.get("normalizedRoutingRules") or ""
        disable_tbc = ctx.get("disableTransferByContext")
        rule_matches = rule_extension_matches(str(ext_num) if ext_num else "", rules_str) if ext_num else []

        row = {
            "conversationId": conversation_id,
            "assistantId": assistant_id,
            "accountId": account_id,
            "firstSeen": first_ts,
            "userTranscripts": user_words,
            "transferTo": transfer_to,
            "transferExtensionNumber": transfer_extension_number,
            "fromFallbackExtension": from_fallback,
            "backupExtensionConfigured": backup,
            "isBackupMatch": (
                (backup and transfer_extension_number and str(backup) == str(transfer_extension_number))
                or (backup and transfer_to and transfer_to.get("extensionNumber") == str(backup))
            ) if (backup and (transfer_extension_number or transfer_to)) else None,
        }
        if context_by_assistant_id is not None:
            row["disableTransferByContext"] = disable_tbc
            row["normalizedRoutingRules"] = rules_str if rules_str else None
            row["transferTargetInRoutingRules"] = rule_matches if rule_matches else None
        result.append(row)
    result.sort(key=lambda x: x.get("firstSeen") or "", reverse=True)
    return result


def main():
    parser = argparse.ArgumentParser(description="Transfer audit: fetch key logs, filter transfer conversations, extract user words / transfer to / backup.")
    parser.add_argument("account_id", help="Account ID (UID), e.g. 37439510")
    parser.add_argument("--last", "-l", default="7d", help="Time range (default: 7d)")
    parser.add_argument("--size", "-n", type=int, default=5000, help="Max logs to fetch (default: 5000)")
    parser.add_argument("--output-dir", "-o", default=None, help="Output directory (default: output/iva_session)")
    parser.add_argument("--format", "-f", choices=["md", "json", "both"], default="both", help="Output format")
    args = parser.parse_args()

    out_dir = Path(args.output_dir) if args.output_dir else ROOT / "output" / "iva_session"
    out_dir.mkdir(parents=True, exist_ok=True)
    base_name = f"transfer_audit_{args.account_id}"

    print(f"🔍 Fetching up to {args.size} assistant_runtime logs (accountId={args.account_id}, last={args.last})...")
    print("   (only fields: @timestamp, message, conversationId, sessionId, accountId)")
    client = KibanaClient.from_env()
    result = fetch_logs(client, args.account_id, args.last, args.size)
    hits = result.get("hits", {}).get("hits", [])
    logs = [h.get("_source", {}) for h in hits]
    print(f"   📥 Fetched {len(logs)} logs")

    # 先得到 transfer 会话的 conversationIds 与 assistantIds，再拉 agent_service 补全 backup
    audit_draft = build_audit(logs, args.account_id, agent_service_by_cid=None, fallback_by_assistant_id=None)
    conversation_ids = [a["conversationId"] for a in audit_draft]
    assistant_ids = list({a["assistantId"] for a in audit_draft if a.get("assistantId")})
    agent_service_by_cid: dict[str, list[dict]] = defaultdict(list)
    fallback_by_assistant_id: dict[str, str] = {}
    if conversation_ids:
        print(f"   🔍 Fetching agent_service by conversationId ({len(conversation_ids)} conv) + by assistantId ({len(assistant_ids)} assistant) for prepare build context...")
        as_logs = fetch_agent_service_logs(client, conversation_ids, args.last)
        for log in as_logs:
            cid = log.get("conversationId")
            if cid:
                agent_service_by_cid[cid].append(log)
        context_by_assistant_id: dict[str, dict] = {}
        if assistant_ids:
            as_by_aid = fetch_agent_service_logs_by_assistant_id(client, assistant_ids, args.last)
            fallback_by_assistant_id = build_fallback_by_assistant_id(as_by_aid)
            context_by_assistant_id = build_context_by_assistant_id(as_by_aid)
            print(f"   📥 Fetched {len(as_logs)} agent_service (by conv) + {len(as_by_aid)} (by assistantId); fallback resolved for {len(fallback_by_assistant_id)} assistant(s)")
        else:
            print(f"   📥 Fetched {len(as_logs)} agent_service logs")
    else:
        context_by_assistant_id = {}

    audit = build_audit(
        logs,
        args.account_id,
        agent_service_by_cid=agent_service_by_cid or None,
        fallback_by_assistant_id=fallback_by_assistant_id or None,
        context_by_assistant_id=context_by_assistant_id or None,
    )
    print(f"   📋 Found {len(audit)} conversations with transfer")

    # 保存原始日志（仅关键字段）供复查
    raw_path = out_dir / f"{base_name}_raw.json"
    with open(raw_path, "w", encoding="utf-8") as f:
        json.dump(logs, f, indent=2, ensure_ascii=False, default=str)
    print(f"   💾 Raw logs (key fields only): {raw_path}")

    if args.format in ("json", "both"):
        json_path = out_dir / f"{base_name}.json"
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(audit, f, indent=2, ensure_ascii=False, default=str)
        print(f"   💾 Audit JSON: {json_path}")

    if args.format in ("md", "both"):
        md_path = out_dir / f"{base_name}.md"
        lines = [
            f"# Transfer Audit — Account {args.account_id}",
            f"",
            f"Time range: {args.last} | Fetched logs: {len(logs)} | Conversations with transfer: {len(audit)}",
            f"",
            f"---",
            f"",
        ]
        for i, row in enumerate(audit, 1):
            lines.append(f"## {i}. {row['conversationId']}")
            lines.append(f"")
            lines.append(f"- **Assistant ID:** {row.get('assistantId') or '(not found)'}")
            lines.append(f"- **First seen:** {row.get('firstSeen')}")
            lines.append(f"- **User words (transcripts):** {row.get('userTranscripts') or '(none extracted)'}")
            lines.append(f"- **Transfer to:** {row.get('transferTo')} (requested extension number: {row.get('transferExtensionNumber')})")
            lines.append(f"- **From backup extension?** `from_fallback_extension`: {row.get('fromFallbackExtension')}")
            lines.append(f"- **Backup extension configured (prepare build context / session):** `{row.get('backupExtensionConfigured') or '(not found)'}`")
            lines.append(f"- **Transfer target == backup?** {row.get('isBackupMatch')}")
            if "disableTransferByContext" in row:
                lines.append(f"- **Transfer by context disabled?** `disableTransferByContext`: {row.get('disableTransferByContext')}")
                rules = row.get("normalizedRoutingRules") or ""
                if rules:
                    lines.append(f"- **Transfer-by-context rules (prepare build context):**")
                    for rline in rules.split("\n")[:12]:
                        rline = rline.strip()
                        prefix = "" if rline.startswith("-") else "  - "
                        lines.append(f"  {prefix}{rline[:180]}{'...' if len(rline) > 180 else ''}")
                    if rules.count("\n") >= 12:
                        lines.append(f"  - ... (see JSON for full normalizedRoutingRules)")
                else:
                    lines.append(f"- **Transfer-by-context rules:** (empty or not found)")
                matches = row.get("transferTargetInRoutingRules")
                if matches:
                    lines.append(f"- **Transfer target in routing rules? (possible transfer-by-context match):** yes — {matches}")
                else:
                    lines.append(f"- **Transfer target in routing rules?** no (or rules empty/disabled)")
            lines.append(f"")
        with open(md_path, "w", encoding="utf-8") as f:
            f.write("\n".join(lines))
        print(f"   💾 Audit Markdown: {md_path}")

    print("")
    print("✅ Done.")
    return 0


if __name__ == "__main__":
    sys.exit(main())

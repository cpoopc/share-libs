#!/bin/bash
# Find accounts with priority service_tier enabled

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
IVA_LOGTRACER_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$IVA_LOGTRACER_DIR/../.." && pwd)"

# Parse arguments
ENV="lab"
TIME_RANGE="last_24h"

while [[ $# -gt 0 ]]; do
    case $1 in
        --env)
            ENV="$2"
            shift 2
            ;;
        last_1h|last_24h|last_7d|last_30d)
            TIME_RANGE="$1"
            shift
            ;;
        *)
            shift
            ;;
    esac
done

ENV_FILE="$IVA_LOGTRACER_DIR/.env.$ENV"
OUTPUT_FILE="$IVA_LOGTRACER_DIR/output/priority_accounts_${ENV}_${TIME_RANGE}.json"

if [ ! -f "$ENV_FILE" ]; then
    echo "❌ Error: Environment file not found: $ENV_FILE"
    echo "Available environments:"
    ls -1 "$IVA_LOGTRACER_DIR"/.env.* | xargs -n1 basename
    exit 1
fi

# Load environment
source "$ENV_FILE"

echo "🔍 Finding accounts with priority service_tier..."
echo "   Environment: $ENV"
echo "   Time range: $TIME_RANGE"
echo ""

# Run Python script
python3 "$SCRIPT_DIR/find_priority_accounts.py" \
    --kibana-url "$KIBANA_URL" \
    --kibana-username "$KIBANA_USERNAME" \
    --kibana-password "$KIBANA_PASSWORD" \
    --time-range "$TIME_RANGE" \
    --output "$OUTPUT_FILE" \
    --verify-certs "$KIBANA_VERIFY_CERTS"

echo ""
echo "✅ Done! Results saved to: $OUTPUT_FILE"

if [ -f "$OUTPUT_FILE" ] && command -v jq &> /dev/null; then
    echo ""
    echo "📊 Summary:"
    jq -r '.summary.total_accounts, .summary.total_requests' "$OUTPUT_FILE" 2>/dev/null | {
        read accounts
        read requests
        echo "   Accounts with priority: $accounts"
        echo "   Total priority requests: $requests"
    } || true
fi

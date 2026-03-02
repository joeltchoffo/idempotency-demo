#!/usr/bin/env bash
set -euo pipefail

API_URL="${API_URL:-http://127.0.0.1:8000}"
KEY="${1:-$(python - <<'PY'
import uuid
print(uuid.uuid4())
PY
)}"

BODY='{"customer_id":"cust_123","currency":"EUR","amount_cents":1999,"items":[{"sku":"sku_abc","qty":1,"unit_price_cents":1999}]}'

echo "Using Idempotency-Key: $KEY"
echo

for i in 1 2 3; do
  echo "---- Request $i ----"
  curl -sS -i \
    -H "Content-Type: application/json" \
    -H "Idempotency-Key: $KEY" \
    -d "$BODY" \
    "$API_URL/orders" | sed 's/\r$//'
  echo
done

echo "Tip: run again with the SAME key to see replayed response."
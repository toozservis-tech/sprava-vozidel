#!/usr/bin/env bash
set -euo pipefail

# Jednoduchý helper pro získání JWT tokenu bez ukládání přihlašovacích údajů do repo
# Použití:
#   EMAIL="user@example.com" PASS="heslo" API="http://127.0.0.1:8000" ./scripts/get_token.sh
# Pokud API není zadáno, použije se http://127.0.0.1:8000

API="${API:-http://127.0.0.1:8000}"
EMAIL="${EMAIL:-}"
PASS="${PASS:-}"

if [[ -z "$EMAIL" || -z "$PASS" ]]; then
  echo "EMAIL a PASS musí být nastaveny v prostředí." >&2
  exit 1
fi

if ! command -v jq >/dev/null 2>&1; then
  echo "Není dostupný jq (nutné pro parsování access_token)." >&2
  exit 1
fi

response="$(curl -sS -X POST "$API/user/login" \
  -H "Content-Type: application/json" \
  -d "{\"email\":\"$EMAIL\",\"password\":\"$PASS\"}")"

token="$(echo "$response" | jq -r '.access_token // empty')"

if [[ -z "$token" || "$token" == "null" ]]; then
  echo "LOGIN_FAIL" >&2
  echo "$response" >&2
  exit 1
fi

echo "$token"
echo "TOKEN_OK (len=${#token})"


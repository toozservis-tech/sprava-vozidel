#!/bin/bash
# Test script pro ověření /api/v1/license/status endpointu

# Použít lokální URL (na serveru) nebo produkční URL
API_URL="${API_URL:-http://127.0.0.1:8000}"

echo "=== Test /api/v1/license/status endpoint ==="
echo "API URL: $API_URL"
echo ""

echo "=== Test 1: Bez tokenu (očekáváno 401, ne 404) ==="
curl -i $API_URL/api/v1/license/status 2>&1 | head -10
echo ""

echo "=== Test 2: Kontrola OpenAPI JSON ==="
if curl -s $API_URL/openapi.json | grep -q "license/status"; then
    echo "✓ 'license/status' nalezeno v openapi.json"
    curl -s $API_URL/openapi.json | grep -A 5 "license/status" | head -10
else
    echo "❌ 'license/status' NENALEZENO v openapi.json"
fi
echo ""

echo "=== Test 3: Kontrola /docs ==="
if curl -s $API_URL/docs | grep -q "license/status"; then
    echo "✓ 'license/status' nalezeno v /docs"
else
    echo "❌ 'license/status' NENALEZENO v /docs"
fi
echo ""

echo "=== Test 4: Další endpointy pro porovnání ==="
echo "GET /api/v1/vehicles (bez tokenu):"
curl -s -o /dev/null -w "HTTP Status: %{http_code}\n" $API_URL/api/v1/vehicles
echo ""
echo ""
echo "=== Pro test s tokenem ==="
echo "TOKEN=\"<váš_token>\""
echo "curl -i $API_URL/api/v1/license/status -H \"Authorization: Bearer \$TOKEN\""

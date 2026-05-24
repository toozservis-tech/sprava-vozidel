#!/bin/bash
# Test script pro ověření admin tenant a license upgrade funkcionality

set -e

BASE_URL="${BASE_URL:-http://127.0.0.1:8000}"
TEST_EMAIL="${TEST_EMAIL:-}"
TEST_PASSWORD="${TEST_PASSWORD:-}"

echo "=== Test License Admin Functionality ==="
echo "BASE_URL: $BASE_URL"
echo ""

# 1. Health check
echo "1. Health check:"
curl -i "$BASE_URL/health" 2>&1 | head -15
echo ""
echo ""

# 2. License status bez tokenu (očekává 401)
echo "2. License status bez tokenu (očekává 401):"
curl -i "$BASE_URL/api/v1/license/status" 2>&1 | head -15
echo ""
echo ""

# 3. Získání tokenu
if [ -z "$TEST_EMAIL" ] || [ -z "$TEST_PASSWORD" ]; then
    echo "3. ⚠️  TEST_EMAIL a TEST_PASSWORD nejsou nastaveny, přeskočím získání tokenu"
    echo "   Pro testování nastavte:"
    echo "   export TEST_EMAIL='<email>'"
    echo "   export TEST_PASSWORD='<heslo>'"
    echo ""
else
    echo "3. Získání tokenu:"
    TOKEN=$(curl -s -X POST "$BASE_URL/user/login" \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}" | \
        python3 -c "import sys,json;print(json.load(sys.stdin).get('access_token',''))")
    
    if [ -z "$TOKEN" ]; then
        echo "   ❌ Nepodařilo se získat token"
        exit 1
    else
        echo "   ✅ Token získán (${TOKEN:0:20}...)"
    fi
    echo ""
    
    # 4. License status s tokenem
    echo "4. License status s tokenem:"
    curl -i "$BASE_URL/api/v1/license/status" \
        -H "Authorization: Bearer $TOKEN" 2>&1 | head -20
    echo ""
    echo ""
    
    # 5. Upgrade plánu (pouze admin role nebo admin tenant)
    echo "5. Upgrade plánu na PREMIUM:"
    curl -i -X POST "$BASE_URL/api/v1/license/upgrade" \
        -H "Content-Type: application/json" \
        -H "Authorization: Bearer $TOKEN" \
        -d '{"plan":"premium"}' 2>&1 | head -20
    echo ""
    echo ""
    
    # 6. Ověření změny
    echo "6. Ověření změny (license status po upgrade):"
    curl -s "$BASE_URL/api/v1/license/status" \
        -H "Authorization: Bearer $TOKEN" | python3 -m json.tool 2>&1 | head -30
    echo ""
fi

echo "=== Test dokončen ==="

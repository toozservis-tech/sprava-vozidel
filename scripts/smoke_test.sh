#!/bin/bash
# Smoke test pro TooZ Hub 2 API
# Testuje základní funkčnost endpointů

set -u

API_URL="${API_URL:-http://localhost:8000}"
TEST_PASSWORD="${TEST_PASSWORD:-testpass123}"
TEST_EMAIL="${TEST_EMAIL:-smoke_$(date +%s)_$RANDOM@example.com}"

echo "=========================================="
echo "TOOZHUB2 API SMOKE TEST"
echo "=========================================="
echo "API URL: $API_URL"
echo ""

# Barvy pro výstup
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Počet neúspěšných testů
FAILURES=0

# Funkce pro test
test_endpoint() {
    local method=$1
    local endpoint=$2
    local data=$3
    local token=$4
    local expected_status=$5
    
    echo -n "Testing $method $endpoint ... "
    
    headers=(-H "Content-Type: application/json")
    if [ -n "$token" ]; then
        headers+=(-H "Authorization: Bearer $token")
    fi
    
    if [ "$method" = "GET" ]; then
        response=$(curl -s -w "\n%{http_code}" -X GET "$API_URL$endpoint" "${headers[@]}")
    else
        response=$(curl -s -w "\n%{http_code}" -X "$method" "$API_URL$endpoint" "${headers[@]}" -d "$data")
    fi
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" = "$expected_status" ]; then
        echo -e "${GREEN}✓${NC} ($http_code)"
        return 0
    else
        echo -e "${RED}✗${NC} (expected $expected_status, got $http_code)"
        echo "Response: $body"
        FAILURES=$((FAILURES + 1))
        return 1
    fi
}

# 1. Health check
echo "1. Health check"
test_endpoint "GET" "/health" "" "" "200" || true
echo ""

# 2. Register
echo "2. Register"
register_response=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/user/register" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\",\"name\":\"Smoke Test User\"}")
register_http_code=$(echo "$register_response" | tail -n1)
register_body=$(echo "$register_response" | sed '$d')

if [ "$register_http_code" = "200" ]; then
    echo -e "${GREEN}✓ Register successful${NC}"
else
    echo -e "${RED}✗ Register failed (${register_http_code})${NC}"
    echo "Response: $register_body"
    FAILURES=$((FAILURES + 1))
fi
echo ""

# 3. Login
echo "3. Login"
login_response=$(curl -s -w "\n%{http_code}" -X POST "$API_URL/user/login" \
    -H "Content-Type: application/json" \
    -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}")
login_http_code=$(echo "$login_response" | tail -n1)
login_body=$(echo "$login_response" | sed '$d')

if [ "$login_http_code" = "200" ]; then
    echo -e "${GREEN}✓ Login successful${NC}"
    TOKEN=$(echo "$login_body" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)
    if [ -z "$TOKEN" ]; then
        echo -e "${YELLOW}⚠ Token not found in response${NC}"
        FAILURES=$((FAILURES + 1))
        TOKEN=""
    else
        echo "Token: ${TOKEN:0:20}..."
    fi
else
    echo -e "${RED}✗ Login failed (${login_http_code})${NC}"
    echo "Response: $login_body"
    FAILURES=$((FAILURES + 1))
    TOKEN=""
fi
echo ""

# 4. Get vehicles (requires auth)
if [ -n "$TOKEN" ]; then
    echo "4. Get vehicles"
    test_endpoint "GET" "/api/v1/vehicles" "" "$TOKEN" "200" || true
    echo ""
    
    echo "5. Get reminders"
    test_endpoint "GET" "/api/v1/reminders" "" "$TOKEN" "200" || true
    echo ""
    
    echo "6. Get reservations"
    test_endpoint "GET" "/api/v1/reservations/my" "" "$TOKEN" "200" || true
    echo ""
else
    echo -e "${YELLOW}⚠ Skipping authenticated tests (no token)${NC}"
    FAILURES=$((FAILURES + 3))
    echo ""
fi

# 7. ARES (no auth required)
echo "7. ARES lookup (test IČO: 27074358)"
test_endpoint "GET" "/user/ares?ico=27074358" "" "" "200" || true
echo ""

# 8. VIN decode (vyžaduje auth)
echo "8. VIN decode (test VIN)"
if [ -n "$TOKEN" ]; then
    test_endpoint "POST" "/api/vehicles/decode-vin" '{"vin":"WVWZZZ1JZ3W386752"}' "$TOKEN" "200" || true
else
    echo -e "${YELLOW}⚠ Skipping VIN decode (no token)${NC}"
    FAILURES=$((FAILURES + 1))
fi
echo ""

echo "=========================================="
echo "SMOKE TEST COMPLETE"
echo "=========================================="

if [ "$FAILURES" -gt 0 ]; then
    echo -e "${RED}Smoke test failed: ${FAILURES} check(s) failed.${NC}"
    exit 1
fi

echo -e "${GREEN}Smoke test passed: all checks OK.${NC}"

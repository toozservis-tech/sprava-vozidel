#!/bin/bash
# Production verification script pro TooZ Hub 2
# Testuje skutečné volání proti produkci

BASE_URL="${BASE_URL:-https://hub.toozservis.cz}"
TEST_EMAIL="${TEST_EMAIL:-}"
TEST_PASSWORD="${TEST_PASSWORD:-}"

echo "=========================================="
echo "TOOZHUB2 PRODUCTION VERIFICATION"
echo "=========================================="
echo "Base URL: $BASE_URL"
echo ""

# Barvy pro výstup
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

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
        response=$(curl -s -w "\n%{http_code}" -X GET "$BASE_URL$endpoint" "${headers[@]}")
    else
        response=$(curl -s -w "\n%{http_code}" -X "$method" "$BASE_URL$endpoint" "${headers[@]}" -d "$data")
    fi
    
    http_code=$(echo "$response" | tail -n1)
    body=$(echo "$response" | sed '$d')
    
    if [ "$http_code" = "$expected_status" ]; then
        echo -e "${GREEN}✓${NC} ($http_code)"
        echo "  Response snippet: ${body:0:200}"
        return 0
    else
        echo -e "${RED}✗${NC} (expected $expected_status, got $http_code)"
        echo "  Response snippet: ${body:0:200}"
        return 1
    fi
}

# 1. Health check
echo "1. Health check"
test_endpoint "GET" "/health" "" "" "200"
echo ""

# 2. Login (pokud jsou credentials)
if [ -n "$TEST_EMAIL" ] && [ -n "$TEST_PASSWORD" ]; then
    echo "2. Login"
    login_response=$(curl -s -X POST "$BASE_URL/user/login" \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}")
    
    http_code=$(curl -s -o /dev/null -w "%{http_code}" -X POST "$BASE_URL/user/login" \
        -H "Content-Type: application/json" \
        -d "{\"email\":\"$TEST_EMAIL\",\"password\":\"$TEST_PASSWORD\"}")
    
    if [ "$http_code" = "200" ]; then
        echo -e "${GREEN}✓ Login successful${NC}"
        TOKEN=$(echo "$login_response" | python3 -c "import sys, json; print(json.load(sys.stdin).get('access_token', ''))" 2>/dev/null)
        if [ -z "$TOKEN" ]; then
            echo -e "${YELLOW}⚠ Token not found in response${NC}"
            TOKEN=""
        else
            echo "  Token: ${TOKEN:0:20}..."
        fi
    else
        echo -e "${RED}✗ Login failed ($http_code)${NC}"
        echo "  Response: $login_response"
        TOKEN=""
    fi
    echo ""
else
    echo -e "${YELLOW}⚠ Skipping login (no credentials provided)${NC}"
    echo "  Set TEST_EMAIL and TEST_PASSWORD environment variables to test authenticated endpoints"
    echo ""
    TOKEN=""
fi

# 3. Debug routes (s tokenem pokud máme)
if [ -n "$TOKEN" ]; then
    echo "3. Debug routes endpoint"
    test_endpoint "GET" "/api/_debug/routes" "" "$TOKEN" "200"
    echo ""
    
    echo "4. Get vehicles (with token)"
    test_endpoint "GET" "/api/v1/vehicles" "" "$TOKEN" "200"
    echo ""
else
    echo -e "${YELLOW}⚠ Skipping authenticated tests (no token)${NC}"
    echo ""
fi

# 5. Test bez tokenu (mělo by vrátit 401 nebo 404)
echo "5. Get vehicles (without token - should fail)"
test_endpoint "GET" "/api/v1/vehicles" "" "" "401"
if [ $? -ne 0 ]; then
    # Pokud není 401, zkusit 404
    test_endpoint "GET" "/api/v1/vehicles" "" "" "404"
fi
echo ""

# 6. ARES (no auth required)
echo "6. ARES lookup (test IČO: 27074358)"
test_endpoint "GET" "/user/ares?ico=27074358" "" "" "200"
echo ""

echo "=========================================="
echo "VERIFICATION COMPLETE"
echo "=========================================="
echo ""
echo "To test manually:"
echo "  curl -X GET '$BASE_URL/health'"
if [ -n "$TOKEN" ]; then
    echo "  curl -X GET '$BASE_URL/api/v1/vehicles' -H 'Authorization: Bearer $TOKEN'"
fi

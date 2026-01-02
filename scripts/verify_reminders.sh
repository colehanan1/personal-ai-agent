#!/bin/bash
# Milton Reminders End-to-End Verification Script

set -e

echo "=================================================="
echo "Milton Reminders System Verification"
echo "=================================================="
echo ""

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m' # No Color

# Check dependencies
echo "1. Checking dependencies..."

check_command() {
    if command -v "$1" &> /dev/null; then
        echo -e "  ${GREEN}✓${NC} $1 found"
        return 0
    else
        echo -e "  ${RED}✗${NC} $1 not found"
        return 1
    fi
}

check_python_package() {
    if python -c "import $1" 2>/dev/null; then
        echo -e "  ${GREEN}✓${NC} Python package '$1' installed"
        return 0
    else
        echo -e "  ${YELLOW}⚠${NC} Python package '$1' not installed"
        return 1
    fi
}

DEPS_OK=true

check_command "python" || DEPS_OK=false
check_command "sqlite3" || DEPS_OK=false
check_command "milton-reminders" || {
    echo -e "  ${RED}✗${NC} milton-reminders CLI not found"
    echo "    Run: pip install -e /home/cole-hanan/milton"
    DEPS_OK=false
}

check_python_package "dateparser" || echo "    Optional: pip install dateparser"
check_python_package "pytz" || echo "    Optional: pip install pytz"

if [ "$DEPS_OK" = false ]; then
    echo ""
    echo -e "${RED}ERROR: Missing required dependencies${NC}"
    exit 1
fi

echo ""

# Check environment
echo "2. Checking environment..."

if [ -z "$NTFY_TOPIC" ]; then
    echo -e "  ${YELLOW}⚠${NC} NTFY_TOPIC not set"
    echo "    Set with: export NTFY_TOPIC=your-topic-name"
    echo "    Continuing with test mode (no notifications will be sent)"
    TEST_MODE=true
else
    echo -e "  ${GREEN}✓${NC} NTFY_TOPIC=$NTFY_TOPIC"
    TEST_MODE=false
fi

NTFY_BASE_URL=${NTFY_BASE_URL:-https://ntfy.sh}
echo -e "  ${GREEN}✓${NC} NTFY_BASE_URL=$NTFY_BASE_URL"

TZ=${TZ:-America/New_York}
echo -e "  ${GREEN}✓${NC} TZ=$TZ"

STATE_DIR=${STATE_DIR:-$HOME/.local/state/milton}
echo -e "  ${GREEN}✓${NC} STATE_DIR=$STATE_DIR"

DB_PATH="$STATE_DIR/reminders.sqlite3"
echo -e "  ${GREEN}✓${NC} Database: $DB_PATH"

echo ""

# Create test reminder
echo "3. Creating test reminder..."

TEST_DB_PATH="/tmp/milton_reminders_test_$$.sqlite3"
trap "rm -f $TEST_DB_PATH" EXIT

# Use a temporary database for testing
export STATE_DIR=/tmp

TEST_MESSAGE="Test reminder $(date +%s)"
TEST_TIME="in 5m"

echo "  Creating reminder: '$TEST_MESSAGE' at '$TEST_TIME'"

OUTPUT=$(milton-reminders add "$TEST_MESSAGE" --when "$TEST_TIME" --json 2>&1) || {
    echo -e "  ${RED}✗${NC} Failed to create reminder"
    echo "  Error: $OUTPUT"
    exit 1
}

REMINDER_ID=$(echo "$OUTPUT" | jq -r '.id' 2>/dev/null) || {
    echo -e "  ${RED}✗${NC} Failed to parse reminder ID"
    echo "  Output: $OUTPUT"
    exit 1
}

echo -e "  ${GREEN}✓${NC} Reminder created with ID: $REMINDER_ID"

# Verify in database
echo ""
echo "4. Verifying database storage..."

DB_COUNT=$(sqlite3 "/tmp/reminders.sqlite3" "SELECT COUNT(*) FROM reminders WHERE id = $REMINDER_ID;" 2>/dev/null) || {
    echo -e "  ${RED}✗${NC} Failed to query database"
    exit 1
}

if [ "$DB_COUNT" -eq 1 ]; then
    echo -e "  ${GREEN}✓${NC} Reminder found in database"
else
    echo -e "  ${RED}✗${NC} Reminder not found in database (count: $DB_COUNT)"
    exit 1
fi

# Show reminder details
DB_RECORD=$(sqlite3 "/tmp/reminders.sqlite3" \
    "SELECT id, message, datetime(due_at, 'unixepoch', 'localtime'), timezone FROM reminders WHERE id = $REMINDER_ID;")
echo "  Record: $DB_RECORD"

# List reminders
echo ""
echo "5. Testing list command..."

LIST_OUTPUT=$(milton-reminders list --json 2>&1) || {
    echo -e "  ${RED}✗${NC} Failed to list reminders"
    exit 1
}

LIST_COUNT=$(echo "$LIST_OUTPUT" | jq 'length' 2>/dev/null) || {
    echo -e "  ${RED}✗${NC} Failed to parse list output"
    exit 1
}

if [ "$LIST_COUNT" -ge 1 ]; then
    echo -e "  ${GREEN}✓${NC} List command works ($LIST_COUNT reminder(s) found)"
else
    echo -e "  ${RED}✗${NC} No reminders found in list"
    exit 1
fi

# Test cancel
echo ""
echo "6. Testing cancel command..."

CANCEL_OUTPUT=$(milton-reminders cancel "$REMINDER_ID" --json 2>&1) || {
    echo -e "  ${RED}✗${NC} Failed to cancel reminder"
    exit 1
}

echo -e "  ${GREEN}✓${NC} Reminder canceled"

# Verify canceled
DB_CANCELED=$(sqlite3 "/tmp/reminders.sqlite3" \
    "SELECT canceled_at IS NOT NULL FROM reminders WHERE id = $REMINDER_ID;")

if [ "$DB_CANCELED" = "1" ]; then
    echo -e "  ${GREEN}✓${NC} Cancellation verified in database"
else
    echo -e "  ${RED}✗${NC} Reminder not marked as canceled"
    exit 1
fi

# Optional: Test ntfy connectivity
echo ""
echo "7. Testing ntfy connectivity (optional)..."

if [ "$TEST_MODE" = true ]; then
    echo -e "  ${YELLOW}⊘${NC} Skipped (NTFY_TOPIC not set)"
else
    TEST_MSG="Milton reminders test $(date +%H:%M:%S)"
    if curl -s -d "$TEST_MSG" -H "Title: Milton Test" "${NTFY_BASE_URL}/${NTFY_TOPIC}" > /dev/null 2>&1; then
        echo -e "  ${GREEN}✓${NC} Test notification sent to ntfy"
        echo "    Check your phone for: '$TEST_MSG'"
    else
        echo -e "  ${YELLOW}⚠${NC} Failed to send test notification"
        echo "    This may be a connectivity issue"
    fi
fi

# Test time parsing
echo ""
echo "8. Testing time parsing..."

test_time_parse() {
    local expr="$1"
    local output=$(milton-reminders add "Test" --when "$expr" --json 2>&1)
    if echo "$output" | jq -e '.id' > /dev/null 2>&1; then
        local id=$(echo "$output" | jq -r '.id')
        milton-reminders cancel "$id" > /dev/null 2>&1
        echo -e "  ${GREEN}✓${NC} '$expr' parsed successfully"
        return 0
    else
        echo -e "  ${RED}✗${NC} '$expr' failed to parse"
        return 1
    fi
}

test_time_parse "in 30m"
test_time_parse "in 2 hours"
test_time_parse "at 14:30"
test_time_parse "2026-12-31 23:59"

if command -v python -c "import dateparser" &> /dev/null 2>&1; then
    test_time_parse "tomorrow at 9am" || echo "    (Natural language parsing may be limited)"
fi

# Summary
echo ""
echo "=================================================="
echo "Verification Complete!"
echo "=================================================="
echo ""
echo -e "${GREEN}✓ All tests passed!${NC}"
echo ""
echo "Next steps:"
echo "  1. Set NTFY_TOPIC: export NTFY_TOPIC=your-topic-name"
echo "  2. Install ntfy app on your phone"
echo "  3. Subscribe to your topic"
echo "  4. Start scheduler: milton-reminders run"
echo "  5. Create a test reminder: milton-reminders add 'Test' --when 'in 2m'"
echo ""
echo "For production deployment:"
echo "  - See docs/reminders.md for systemd setup"
echo "  - Run: cp systemd/milton-reminders.service ~/.config/systemd/user/"
echo "  - Then: systemctl --user enable milton-reminders"
echo ""

# Cleanup
rm -f "/tmp/reminders.sqlite3"

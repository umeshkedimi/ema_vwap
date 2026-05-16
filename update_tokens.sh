#!/bin/bash
# Token Update Script for EMA-VWAP Trading Bot
# Run this from your Mac before 9 AM daily

SERVER="root@64.227.163.187"
SSH_KEY="~/.ssh/id_ed25519_ai_dev"
CONFIG_PATH="/root/ema_vwap/config.env"

echo "=========================================="
echo "  Token Update for Trading Bot"
echo "=========================================="
echo ""

# Get Fyers token
echo "1. Login to Fyers and get access token"
echo "   URL: https://api-t1.fyers.in/api/v3/generate-authcode?client_id=O175VKW4UD-200&redirect_uri=https://trade.fyers.in/api-login/redirect-uri/index.html&response_type=code&state=sample_state"
echo ""
read -p "Paste FYERS access token: " FYERS_TOKEN
echo ""

# Get Kite token
echo "2. Login to Kite and get access token"
echo "   (Use your usual Kite token generation process)"
echo ""
read -p "Paste KITE access token: " KITE_TOKEN
echo ""

if [ -z "$FYERS_TOKEN" ] || [ -z "$KITE_TOKEN" ]; then
    echo "Error: Both tokens are required!"
    exit 1
fi

echo "Updating tokens on server..."

# Update tokens on server using sed
ssh -i $SSH_KEY $SERVER "
    sed -i 's|^FYERS_ACCESS_TOKEN=.*|FYERS_ACCESS_TOKEN=$FYERS_TOKEN|' $CONFIG_PATH
    sed -i 's|^KITE_ACCESS_TOKEN=.*|KITE_ACCESS_TOKEN=$KITE_TOKEN|' $CONFIG_PATH
"

if [ $? -eq 0 ]; then
    echo ""
    echo "=========================================="
    echo "  Tokens updated successfully!"
    echo "=========================================="
    echo ""
    echo "Verifying..."
    ssh -i $SSH_KEY $SERVER "grep -E '^(FYERS_ACCESS_TOKEN|KITE_ACCESS_TOKEN)' $CONFIG_PATH | cut -c1-40"
    echo "..."
    echo ""
    echo "Bot will run automatically at 9:10 AM"
else
    echo "Error updating tokens!"
    exit 1
fi

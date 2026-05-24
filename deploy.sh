#!/bin/bash
set -e

echo "=== TOOZHUB2 FAST DEPLOY START ==="

cd /opt/toozhub2/app

systemctl restart toozhub2
sleep 2
systemctl --no-pager --full status toozhub2

echo "=== TOOZHUB2 FAST DEPLOY DONE ==="

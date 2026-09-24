#!/bin/bash
# DB-IP IP to Country Lite (CC BY 4.0, 매달 갱신) → data/geoip/dbip-country-lite.mmdb. 이번 달 파일이 아직 없으면 지난달 것.
set -e
cd "$(dirname "$0")/.."
mkdir -p data/geoip
for m in $(date +%Y-%m) $(date -v-1m +%Y-%m 2>/dev/null || date -d '1 month ago' +%Y-%m); do
  if curl -sfL -o data/geoip/dbip.mmdb.gz "https://download.db-ip.com/free/dbip-country-lite-$m.mmdb.gz"; then
    gunzip -f data/geoip/dbip.mmdb.gz && mv data/geoip/dbip.mmdb data/geoip/dbip-country-lite.mmdb && echo "DB-IP $m" && exit 0
  fi
done
echo "DB-IP 다운로드 실패"; exit 1

#!/bin/bash
# Geofabrik 일본 지역별 OSM pbf 8개 → data/raw/osm_pbf/ (약 2.5GB). Overpass 는 과부하로 쓰지 않음.
# 사용: bash scripts/download_osm.sh   (이미 있는 파일은 건너뜀)
set -e
cd "$(dirname "$0")/.."
mkdir -p data/raw/osm_pbf
for r in hokkaido tohoku kanto chubu kansai chugoku shikoku kyushu; do
  f=data/raw/osm_pbf/$r-latest.osm.pbf
  [ -f "$f" ] && { echo "있음 $f"; continue; }
  curl -fL --retry 3 -o "$f" "https://download.geofabrik.de/asia/japan/$r-latest.osm.pbf"
done
ls -la data/raw/osm_pbf

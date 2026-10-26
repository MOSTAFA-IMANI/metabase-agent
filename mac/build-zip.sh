#!/bin/bash
# Rebuild download/Soupop-Data-mac.zip from mac/Soupop Data.app (keeps the executable bit).
cd "$(dirname "$0")" || exit 1
mkdir -p ../download
rm -f ../download/Soupop-Data-mac.zip
zip -qry ../download/Soupop-Data-mac.zip "Soupop Data.app" -x "*.DS_Store"
echo "Built download/Soupop-Data-mac.zip"

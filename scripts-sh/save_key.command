#!/bin/bash
# Saves a Metabase API key into ~/soupop-data/.env and checks that it works.
cd "$HOME/soupop-data" || exit 1
echo "Paste your Metabase API key and press Enter (nothing shows while you paste):"
read -rs KEY
KEY="$(printf '%s' "$KEY" | tr -d '[:space:]')"
if [ -z "$KEY" ]; then echo "No key received. Run this again."; exit 1; fi
touch .env && chmod 600 .env
grep -v -E '^(METABASE_URL|METABASE_API_KEY|METABASE_DATABASE_ID)=' .env > .env.tmp 2>/dev/null
{ echo "METABASE_URL=https://mt.soupop.ir"; echo "METABASE_API_KEY=$KEY"; echo "METABASE_DATABASE_ID=2"; cat .env.tmp; } > .env
rm -f .env.tmp; chmod 600 .env
CODE=$(curl -s -o /dev/null -w "%{http_code}" -H "X-API-Key: $KEY" https://mt.soupop.ir/api/user/current)
if [ "$CODE" = "200" ]; then echo "Saved. The key works."; else echo "Saved, but Metabase answered $CODE. The key may be wrong; make a new one and run this again."; fi

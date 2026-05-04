import os, sys
for line in open('.env'):
    line = line.strip()
    if line and not line.startswith('#') and '=' in line:
        k, v = line.split('=', 1)
        os.environ.setdefault(k, v)
sys.path.insert(0, '.')
from scripts.shared import get_db_url, is_postgres
from scripts.sector_flow import load_watchlist, get_connection, fetch_sector_flow, format_flow_terminal, fetch_volume_baselines

core = load_watchlist()
conn = get_connection(get_db_url())
print('Connected, fetching flow...')
flow = fetch_sector_flow(conn, core)
print(f'Got {len(flow.sectors)} sectors')
baselines = fetch_volume_baselines(conn, core, days=5)
format_flow_terminal(flow, baselines)
conn.close()

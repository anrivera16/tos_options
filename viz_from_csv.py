import os
import csv
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import numpy as np
from datetime import datetime
from collections import defaultdict

CSV_PATH = "/Users/arivera/projects/project_go/2026-03-27-StockAndOptionQuoteForSPY.csv"

def parse_header_info(filepath):
    underlying = None
    with open(filepath, 'r', encoding='utf-8-sig') as f:
        for i, line in enumerate(f):
            if i > 10:
                break
            parts = line.strip().split(',')
            if len(parts) >= 4 and underlying is None:
                try:
                    val = float(parts[0])
                    if 10 < val < 100000:
                        underlying = val
                except:
                    pass
    return underlying

UNDERLYING = parse_header_info(CSV_PATH)
print(f"Underlying: ${UNDERLYING:.2f}")

options = []
with open(CSV_PATH, 'r', encoding='utf-8-sig') as f:
    reader = csv.reader(f)
    for row in reader:
        if len(row) < 30:
            continue
        try:
            exp = row[19]
            strike = float(row[20])
            if not exp or strike == 0:
                continue
            
            dte = int(float(row[21])) if row[21] and row[21].replace('.', '').isdigit() else 0
            if dte == 0:
                continue
            
            put_vol = int(row[2]) if row[2] and row[2].isdigit() else 0
            put_oi = int(row[3]) if row[3] and row[3].isdigit() else 0
            put_delta = float(row[5]) if row[5] else 0
            put_gamma = float(row[6]) if row[6] else 0
            put_iv_str = row[7].replace('%', '') if row[7] else '0'
            put_iv = float(put_iv_str) / 100 if put_iv_str.replace('.', '').replace('-', '').isdigit() else 0
            put_theta = float(row[13]) if row[13] else 0
            put_vega = float(row[14]) if row[14] else 0
            put_bid = float(row[15]) if row[15] else 0
            put_ask = float(row[17]) if row[17] else 0
            
            call_bid = float(row[21]) if row[21] else 0
            call_ask = float(row[23]) if row[23] else 0
            call_vol = int(row[25]) if row[25] and row[25].isdigit() else 0
            call_oi = int(row[26]) if row[26] and row[26].isdigit() else 0
            call_delta = float(row[28]) if row[28] else 0
            call_gamma = float(row[29]) if row[29] else 0
            call_iv_str = row[30].replace('%', '') if row[30] else '0'
            call_iv = float(call_iv_str) / 100 if call_iv_str.replace('.', '').replace('-', '').isdigit() else 0
            call_theta = float(row[36]) if row[36] else 0
            call_vega = float(row[37]) if row[37] else 0
            
            if call_iv > 0 or put_iv > 0:
                options.append({
                    'exp': exp,
                    'dte': dte,
                    'strike': strike,
                    'put_delta': put_delta, 'put_gamma': put_gamma, 'put_theta': put_theta, 'put_vega': put_vega,
                    'put_iv': put_iv, 'put_oi': put_oi, 'put_vol': put_vol,
                    'call_delta': call_delta, 'call_gamma': call_gamma, 'call_theta': call_theta, 'call_vega': call_vega,
                    'call_iv': call_iv, 'call_oi': call_oi, 'call_vol': call_vol,
                })
        except (ValueError, IndexError) as e:
            continue

print(f"Parsed {len(options)} option rows")

by_dte = defaultdict(list)
for o in options:
    by_dte[o['dte']].append(o)

dtes = sorted(by_dte.keys())
print(f"DTEs: {dtes[:10]}...")

if not options:
    print("No options parsed!")
    exit(1)

plt.rcParams.update({
    'figure.facecolor': '#1a1a2e',
    'axes.facecolor': '#16213e',
    'axes.edgecolor': '#0f3460',
    'axes.labelcolor': '#e0e0e0',
    'text.color': '#e0e0e0',
    'xtick.color': '#b0b0b0',
    'ytick.color': '#b0b0b0',
    'grid.color': '#0f3460',
    'grid.alpha': 0.4,
})

CALL_COLOR = '#00e676'
PUT_COLOR = '#ff5252'
SPOT_COLOR = '#ffd740'

# Chart 1: IV Smile
fig, ax = plt.subplots(figsize=(14, 8))
palette = ['#00e5ff', '#00e676', '#ffd740', '#ff6e40', '#e040fb', '#448aff', '#ff5252']
target_dtes = sorted(dtes)[:7]

for i, dte in enumerate(target_dtes):
    data = by_dte[dte]
    label = f"{data[0]['exp']} ({dte}d)"
    strikes = [o['strike'] for o in data if o['call_iv'] > 0.05]
    ivs = [o['call_iv'] * 100 for o in data if o['call_iv'] > 0.05]
    if strikes:
        ax.plot(strikes, ivs, label=label, color=palette[i % len(palette)], linewidth=2, alpha=0.85)

ax.axvline(x=UNDERLYING, color=SPOT_COLOR, linestyle='--', alpha=0.7, linewidth=2, label=f'Spot ${UNDERLYING:.0f}')
ax.set_xlabel('Strike Price ($)', fontsize=12)
ax.set_ylabel('Implied Volatility (%)', fontsize=12)
ax.set_title(f'SPY Call IV Skew by Expiration | Spot: ${UNDERLYING:.2f}', fontsize=14, fontweight='bold')
ax.legend(loc='upper right', fontsize=9)
ax.grid(True)
plt.tight_layout()
plt.savefig('/Users/arivera/projects/project_go/spy_1_iv_skew.png', dpi=150)
plt.close()
print("1/8 saved")

# Chart 2: IV Term Structure
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

dtes_plot, call_ivs, put_ivs = [], [], []
for dte in sorted(dtes):
    if dte < 1:
        continue
    data = by_dte[dte]
    atm = min(data, key=lambda x: abs(x['strike'] - UNDERLYING))
    if atm['call_iv'] > 0.01:
        dtes_plot.append(dte)
        call_ivs.append(atm['call_iv'] * 100)
        put_ivs.append(atm['put_iv'] * 100 if atm['put_iv'] > 0 else 0)

ax1.plot(dtes_plot, call_ivs, 'o-', color='#00e5ff', linewidth=2, markersize=7, label='Call ATM IV')
ax1.plot(dtes_plot, put_ivs, 's--', color='#ff5252', linewidth=2, markersize=6, label='Put ATM IV', alpha=0.8)
for d, iv, lbl in zip(dtes_plot, call_ivs, dtes_plot):
    if d < 400:
        ax1.annotate(f'{iv:.1f}%', (d, iv), textcoords="offset points", xytext=(0, 10), ha='center', fontsize=7, color='#b0b0b0')
ax1.set_xlabel('Days to Expiration')
ax1.set_ylabel('ATM Implied Volatility (%)')
ax1.set_title('IV Term Structure (ATM)', fontsize=13, fontweight='bold')
ax1.legend(fontsize=9)
ax1.grid(True)
if dtes_plot:
    ax1.set_xlim(-5, max(dtes_plot) + 30)

# 25D Skew
skew_dtes, skew_vals = [], []
for dte in sorted(dtes):
    if dte < 2:
        continue
    data = by_dte[dte]
    puts_25d = [o for o in data if 0.20 < abs(o['put_delta']) < 0.30 and o['put_iv'] > 0]
    calls_25d = [o for o in data if 0.20 < abs(o['call_delta']) < 0.30 and o['call_iv'] > 0]
    if puts_25d and calls_25d:
        skew_dtes.append(dte)
        skew_vals.append(np.mean([o['put_iv'] for o in puts_25d]) * 100 - np.mean([o['call_iv'] for o in calls_25d]) * 100)

if skew_dtes:
    ax2.bar(skew_dtes, skew_vals, width=max(1, max(skew_dtes) * 0.02), 
            color=['#ff5252' if v > 0 else '#00e676' for v in skew_vals], alpha=0.8)
ax2.axhline(y=0, color='white', linewidth=0.5, alpha=0.5)
ax2.set_xlabel('Days to Expiration')
ax2.set_ylabel('25D Put IV - 25D Call IV (%)')
ax2.set_title('Volatility Skew (25D Risk Reversal)', fontsize=13, fontweight='bold')
ax2.grid(True)
plt.tight_layout()
plt.savefig('/Users/arivera/projects/project_go/spy_2_term_structure.png', dpi=150)
plt.close()
print("2/8 saved")

# Chart 3: OI Distribution
fig, axes = plt.subplots(2, 2, figsize=(16, 12))
display_dtes = [d for d in sorted(dtes) if d > 0][:4]

for idx, dte in enumerate(display_dtes[:4]):
    ax = axes[idx // 2][idx % 2]
    data = by_dte[dte]
    exp_label = data[0]['exp']
    
    filtered = [o for o in data if o['call_oi'] > 0 or o['put_oi'] > 0]
    strikes = [o['strike'] for o in filtered]
    call_oi = [o['call_oi'] for o in filtered]
    put_oi = [o['put_oi'] for o in filtered]
    
    w = max(1, (max(strikes) - min(strikes)) / len(strikes) * 0.4) if len(strikes) > 1 else 1
    
    ax.bar(strikes, call_oi, width=w, label='Call OI', color=CALL_COLOR, alpha=0.7)
    ax.bar(strikes, [-p for p in put_oi], width=w, label='Put OI', color=PUT_COLOR, alpha=0.7)
    ax.axvline(x=UNDERLYING, color=SPOT_COLOR, linestyle='--', alpha=0.7, linewidth=2, label=f'Spot')
    ax.axhline(y=0, color='white', linewidth=0.3)
    ax.set_title(f'{exp_label} ({dte} DTE)', fontsize=11, fontweight='bold')
    ax.set_xlabel('Strike ($)')
    ax.set_ylabel('Open Interest (Calls ↑ / Puts ↓)')
    ax.legend(fontsize=7, loc='upper right')
    ax.grid(True)
    ax.tick_params(axis='x', rotation=45, labelsize=7)

fig.suptitle('SPY Open Interest Distribution', fontsize=14, fontweight='bold', y=1.01)
plt.tight_layout()
plt.savefig('/Users/arivera/projects/project_go/spy_3_oi_distribution.png', dpi=150)
plt.close()
print("3/8 saved")

# GEX Calculation
def compute_gex_by_strike(option_rows, strike_min=560, strike_max=780):
    gex_map = defaultdict(lambda: {'call_gex': 0, 'put_gex': 0, 'call_oi': 0, 'put_oi': 0})
    for o in option_rows:
        s = o['strike']
        if s < strike_min or s > strike_max:
            continue
        call_gex = o['call_gamma'] * o['call_oi'] * 100 * UNDERLYING
        put_gex = -o['put_gamma'] * o['put_oi'] * 100 * UNDERLYING
        gex_map[s]['call_gex'] += call_gex
        gex_map[s]['put_gex'] += put_gex
        gex_map[s]['call_oi'] += o['call_oi']
        gex_map[s]['put_oi'] += o['put_oi']
    return dict(sorted(gex_map.items()))

total_gex = compute_gex_by_strike(options)
strikes_all = np.array(list(total_gex.keys()))
call_gex_all = np.array([total_gex[s]['call_gex'] for s in strikes_all])
put_gex_all = np.array([total_gex[s]['put_gex'] for s in strikes_all])
net_gex_all = call_gex_all + put_gex_all

# Chart 4: GEX Profile
fig, (ax1, ax2) = plt.subplots(2, 1, figsize=(16, 14), gridspec_kw={'height_ratios': [2, 1]})

mask = (strikes_all >= 590) & (strikes_all <= 750)
s_plot = strikes_all[mask]
cg = call_gex_all[mask] / 1e6
pg = put_gex_all[mask] / 1e6
ng = net_gex_all[mask] / 1e6

bar_w = np.median(np.diff(s_plot)) * 0.6 if len(s_plot) > 1 else 1

ax1.bar(s_plot, cg, width=bar_w, label='Call GEX (dealers long)', color=CALL_COLOR, alpha=0.6)
ax1.bar(s_plot, pg, width=bar_w, label='Put GEX (dealers short)', color=PUT_COLOR, alpha=0.6)
ax1.plot(s_plot, ng, color='#00e5ff', linewidth=2.5, label='Net GEX', zorder=5)
ax1.axhline(y=0, color='white', linewidth=0.5, alpha=0.5)
ax1.axvline(x=UNDERLYING, color=SPOT_COLOR, linestyle='--', linewidth=2, alpha=0.8, label=f'Spot ${UNDERLYING:.0f}')
ax1.set_xlabel('Strike Price ($)', fontsize=11)
ax1.set_ylabel('Gamma Exposure ($M)', fontsize=11)
ax1.set_title(f'SPY Gamma Exposure (GEX) Profile\nSpot: ${UNDERLYING:.2f}', fontsize=13, fontweight='bold')
ax1.legend(loc='upper left', fontsize=9, ncol=2)
ax1.grid(True)

cum_gex = np.cumsum(net_gex_all[mask]) / 1e6
ax2.fill_between(s_plot, 0, cum_gex, where=(cum_gex >= 0), color=CALL_COLOR, alpha=0.3, interpolate=True)
ax2.fill_between(s_plot, 0, cum_gex, where=(cum_gex < 0), color=PUT_COLOR, alpha=0.3, interpolate=True)
ax2.plot(s_plot, cum_gex, color='#00e5ff', linewidth=2)
ax2.axhline(y=0, color='white', linewidth=0.5, alpha=0.5)
ax2.axvline(x=UNDERLYING, color=SPOT_COLOR, linestyle='--', linewidth=2, alpha=0.8)
ax2.set_xlabel('Strike Price ($)', fontsize=11)
ax2.set_ylabel('Cumulative Net GEX ($M)', fontsize=11)
ax2.set_title('Cumulative GEX', fontsize=11)
ax2.grid(True)
plt.tight_layout()
plt.savefig('/Users/arivera/projects/project_go/spy_4_gex_profile.png', dpi=150)
plt.close()
print("4/8 saved")

# Chart 5: GEX by Expiry
fig, axes = plt.subplots(2, 3, figsize=(20, 12))
gex_dtes = [d for d in sorted(dtes) if d >= 2 and d <= 100][:6]

for idx, dte in enumerate(gex_dtes[:6]):
    ax = axes[idx // 3][idx % 3]
    data = by_dte[dte]
    exp_label = data[0]['exp']
    
    gex = compute_gex_by_strike(data, 600, 730)
    if not gex:
        continue
    
    strikes_e = np.array(list(gex.keys()))
    call_gex_e = np.array([gex[s]['call_gex'] for s in strikes_e]) / 1e6
    put_gex_e = np.array([gex[s]['put_gex'] for s in strikes_e]) / 1e6
    net_gex_e = call_gex_e + put_gex_e
    
    bw = np.median(np.diff(strikes_e)) * 0.6 if len(strikes_e) > 1 else 1
    
    ax.bar(strikes_e, call_gex_e, width=bw, color=CALL_COLOR, alpha=0.5, label='Call GEX')
    ax.bar(strikes_e, put_gex_e, width=bw, color=PUT_COLOR, alpha=0.5, label='Put GEX')
    ax.plot(strikes_e, net_gex_e, color='#00e5ff', linewidth=2, label='Net', zorder=5)
    ax.axhline(y=0, color='white', linewidth=0.3)
    ax.axvline(x=UNDERLYING, color=SPOT_COLOR, linestyle='--', linewidth=1.5, alpha=0.8)
    ax.set_title(f'{exp_label} ({dte}d)', fontsize=11, fontweight='bold')
    ax.set_xlabel('Strike ($)', fontsize=8)
    ax.set_ylabel('GEX ($M)', fontsize=8)
    ax.legend(fontsize=6, loc='upper right')
    ax.grid(True)
    ax.tick_params(axis='x', rotation=45, labelsize=7)

fig.suptitle('SPY Gamma Exposure by Expiration', fontsize=14, fontweight='bold', y=1.01)
plt.tight_layout()
plt.savefig('/Users/arivera/projects/project_go/spy_5_gex_by_expiry.png', dpi=150)
plt.close()
print("5/8 saved")

# Chart 6: GEX Key Levels
fig, axes = plt.subplots(1, 3, figsize=(20, 8))

ax = axes[0]
call_gex_dict = {s: cg for s, cg in zip(strikes_all, call_gex_all) if 600 <= s <= 730}
top_call = sorted(call_gex_dict.items(), key=lambda x: x[1], reverse=True)[:15]
if top_call:
    tc_strikes = [x[0] for x in top_call]
    tc_vals = [x[1] / 1e6 for x in top_call]
    tc_strikes, tc_vals = zip(*sorted(zip(tc_strikes, tc_vals)))
    colors_c = [CALL_COLOR if s <= UNDERLYING else '#448aff' for s in tc_strikes]
    ax.barh(range(len(tc_strikes)), tc_vals, color=colors_c, alpha=0.8, height=0.6)
    ax.set_yticks(range(len(tc_strikes)))
    ax.set_yticklabels([f'${s:.0f}' for s in tc_strikes], fontsize=9)
    ax.set_xlabel('Call GEX ($M)', fontsize=10)
    ax.set_title('Call Gamma Walls', fontsize=10, fontweight='bold')
    ax.grid(True, axis='x')

ax = axes[1]
put_gex_dict = {s: pg for s, pg in zip(strikes_all, put_gex_all) if 580 <= s <= 730}
top_put = sorted(put_gex_dict.items(), key=lambda x: abs(x[1]), reverse=True)[:15]
if top_put:
    tp_strikes = [x[0] for x in top_put]
    tp_vals = [x[1] / 1e6 for x in top_put]
    tp_strikes, tp_vals = zip(*sorted(zip(tp_strikes, tp_vals)))
    colors_p = [PUT_COLOR if s <= UNDERLYING else '#ff8a65' for s in tp_strikes]
    ax.barh(range(len(tp_strikes)), tp_vals, color=colors_p, alpha=0.8, height=0.6)
    ax.set_yticks(range(len(tp_strikes)))
    ax.set_yticklabels([f'${s:.0f}' for s in tp_strikes], fontsize=9)
    ax.set_xlabel('Put GEX ($M)', fontsize=10)
    ax.set_title('Put Gamma Walls', fontsize=10, fontweight='bold')
    ax.grid(True, axis='x')

ax = axes[2]
key_strikes = np.arange(600, 730, 5)
key_net = []
for ks in key_strikes:
    closest_idx = np.argmin(np.abs(strikes_all - ks))
    if abs(strikes_all[closest_idx] - ks) < 3:
        key_net.append(net_gex_all[closest_idx] / 1e6)
    else:
        key_net.append(0)
key_net = np.array(key_net)
colors_key = [CALL_COLOR if v > 0 else PUT_COLOR for v in key_net]
ax.barh(range(len(key_strikes)), key_net, color=colors_key, alpha=0.7, height=0.7)
ax.set_yticks(range(len(key_strikes)))
ax.set_yticklabels([f'${s:.0f}' for s in key_strikes], fontsize=8)
ax.axvline(x=0, color='white', linewidth=0.5, alpha=0.5)
ax.set_xlabel('Net GEX ($M)', fontsize=10)
ax.set_title('Net GEX Level Map', fontsize=10, fontweight='bold')
ax.grid(True, axis='x')
plt.tight_layout()
plt.savefig('/Users/arivera/projects/project_go/spy_6_gex_key_levels.png', dpi=150)
plt.close()
print("6/8 saved")

# Chart 7: Theta Decay
fig, (ax1, ax2) = plt.subplots(1, 2, figsize=(16, 7))

for i, dte in enumerate([d for d in sorted(dtes) if 2 <= d <= 60][:5]):
    data = by_dte[dte]
    exp_label = data[0]['exp']
    filtered = [o for o in data if 630 <= o['strike'] <= 700 and o['call_theta'] < 0]
    strikes = [o['strike'] for o in filtered]
    thetas = [abs(o['call_theta']) for o in filtered]
    ax1.plot(strikes, thetas, linewidth=2, label=f'{exp_label} ({dte}d)', color=palette[i % len(palette)])

ax1.axvline(x=UNDERLYING, color=SPOT_COLOR, linestyle='--', alpha=0.7, label='Spot')
ax1.set_xlabel('Strike ($)')
ax1.set_ylabel('|Theta| ($ decay/day)')
ax1.set_title('Call Theta Decay by Strike', fontsize=13, fontweight='bold')
ax1.legend(fontsize=9)
ax1.grid(True)

atm_thetas, theta_dtes = [], []
for dte in sorted(dtes):
    if dte < 1:
        continue
    data = by_dte[dte]
    atm = min(data, key=lambda x: abs(x['strike'] - UNDERLYING))
    if atm['call_theta'] < 0:
        theta_dtes.append(dte)
        atm_thetas.append(abs(atm['call_theta']))

ax2.bar(theta_dtes, atm_thetas, width=max(1, max(theta_dtes) * 0.02 if theta_dtes else 1), color='#ff5252', alpha=0.8)
ax2.set_xlabel('Days to Expiration')
ax2.set_ylabel('|ATM Theta| ($/day)')
ax2.set_title('ATM Theta Term Structure', fontsize=13, fontweight='bold')
ax2.grid(True)
plt.tight_layout()
plt.savefig('/Users/arivera/projects/project_go/spy_7_theta_decay.png', dpi=150)
plt.close()
print("7/8 saved")

# Chart 8: Max Pain & PCR
fig, axes = plt.subplots(1, 3, figsize=(20, 7))

sorted_dtes_list = sorted(dtes)
dte_target = min([d for d in sorted_dtes_list if d >= 20], key=lambda d: d, default=sorted_dtes_list[-1] if sorted_dtes_list else 0)
data = by_dte[dte_target]
exp_label = data[0]['exp']

filtered = [o for o in data if o['call_oi'] > 0 or o['put_oi'] > 0]
strikes = np.array([o['strike'] for o in filtered])
call_oi_arr = np.array([o['call_oi'] for o in filtered])
put_oi_arr = np.array([o['put_oi'] for o in filtered])

pain = np.zeros(len(strikes))
for i, s in enumerate(strikes):
    call_pain = np.sum(np.maximum(s - strikes, 0) * call_oi_arr)
    put_pain = np.sum(np.maximum(strikes - s, 0) * put_oi_arr)
    pain[i] = call_pain + put_pain

max_pain_idx = np.argmin(pain)
max_pain_strike = strikes[max_pain_idx]

ax = axes[0]
ax.plot(strikes, pain / 1e6, color='#e040fb', linewidth=2)
ax.axvline(x=max_pain_strike, color='#ffd740', linestyle='--', linewidth=2, label=f'Max Pain ${max_pain_strike:.0f}')
ax.axvline(x=UNDERLYING, color='#ffd740', linestyle=':', alpha=0.7, label=f'Spot ${UNDERLYING:.0f}')
ax.set_xlabel('Strike ($)')
ax.set_ylabel('Total Pain ($M)')
ax.set_title(f'Max Pain - {exp_label} ({dte_target}d)', fontsize=11, fontweight='bold')
ax.legend(fontsize=9)
ax.grid(True)

ax = axes[1]
ratios, ratio_strikes = [], []
for o in filtered:
    if o['call_oi'] > 100:
        ratios.append(o['put_oi'] / o['call_oi'])
        ratio_strikes.append(o['strike'])

colors_bar = [PUT_COLOR if r > 1 else CALL_COLOR for r in ratios]
ax.bar(ratio_strikes, ratios, width=2, color=colors_bar, alpha=0.7)
ax.axhline(y=1.0, color='white', linestyle='--', linewidth=1, alpha=0.5, label='P/C = 1.0')
ax.axvline(x=UNDERLYING, color='#ffd740', linestyle=':', alpha=0.7, label='Spot')
ax.set_xlabel('Strike ($)')
ax.set_ylabel('Put/Call OI Ratio')
ax.set_title(f'P/C OI Ratio - {exp_label}', fontsize=11, fontweight='bold')
ax.legend(fontsize=9)
ax.grid(True)

ax = axes[2]
pc_dtes, pc_ratios = [], []
for dte in sorted(dtes):
    if dte < 1:
        continue
    data = by_dte[dte]
    total_call_oi = sum(o['call_oi'] for o in data)
    total_put_oi = sum(o['put_oi'] for o in data)
    if total_call_oi > 0:
        pc_dtes.append(dte)
        pc_ratios.append(total_put_oi / total_call_oi)

bar_colors = [PUT_COLOR if r > 1 else CALL_COLOR for r in pc_ratios]
ax.bar(pc_dtes, pc_ratios, width=max(1, max(pc_dtes) * 0.02 if pc_dtes else 1), color=bar_colors, alpha=0.8)
ax.axhline(y=1.0, color='white', linestyle='--', linewidth=1, alpha=0.5, label='P/C = 1.0')
ax.set_xlabel('Days to Expiration')
ax.set_ylabel('Total Put/Call OI Ratio')
ax.set_title('Put/Call Ratio Term Structure', fontsize=11, fontweight='bold')
ax.legend(fontsize=9)
ax.grid(True)
plt.tight_layout()
plt.savefig('/Users/arivera/projects/project_go/spy_8_maxpain_pcr.png', dpi=150)
plt.close()
print("8/8 saved")

print("\nAll charts saved!")

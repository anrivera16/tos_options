#!/bin/bash
# Load .env and run the script
export $(grep -v '^#' .env | xargs)
python3 scripts/backtest_iv_skew.py

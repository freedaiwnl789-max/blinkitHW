#!/bin/bash
# Start Zepto Checker Script

echo "Starting Zepto Product Checker..."
cd "$(dirname "$0")"
python3 zepto_checker.py

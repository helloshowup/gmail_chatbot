#!/bin/bash
# Simple setup script for installing project dependencies
set -e

if [ -f "requirements.txt" ]; then
    pip install -r requirements.txt
else
    echo "requirements.txt not found"
    exit 1
fi

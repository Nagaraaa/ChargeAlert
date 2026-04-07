#!/usr/bin/env bash
# Script compilateur pour Render
pip install --upgrade pip
pip install -r requirements.txt
playwright install chromium
playwright install-deps

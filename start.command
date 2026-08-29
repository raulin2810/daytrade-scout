#!/bin/bash
cd "$(dirname "$0")"
chmod +x start.sh
./start.sh
read -r -p "Fenster schließen mit Enter …" _

#!/bin/bash
set -e
cd "$(dirname "$0")/.."
mkdir -p assets/diagrams

SCENES="CoreLoop ParticleFilter SimulationModes DataFlow ReviewInterval"
OUTNAMES="core-loop particle-filter simulation-modes data-flow review-interval"

scenes_arr=($SCENES)
names_arr=($OUTNAMES)

for i in "${!scenes_arr[@]}"; do
    scene="${scenes_arr[$i]}"
    name="${names_arr[$i]}"
    echo "Rendering $scene..."
    uv run manim render -ql --format=png -s visualizations/scenes.py "$scene"
done

# Find and copy rendered PNGs to assets/diagrams/
for i in "${!scenes_arr[@]}"; do
    scene="${scenes_arr[$i]}"
    name="${names_arr[$i]}"
    png=$(find media/ -name "${scene}.png" -type f 2>/dev/null | head -1)
    if [ -n "$png" ]; then
        cp "$png" "assets/diagrams/${name}.png"
        echo "  -> assets/diagrams/${name}.png"
    else
        echo "  WARNING: Could not find rendered PNG for $scene"
    fi
done

echo "Done. Rendered images in assets/diagrams/"

#!/bin/bash
# Benchmate Setup Script
# Run this after cloning the repository on a new Mac

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SKILLS_DIR="$HOME/.claude/skills"

echo "Setting up Benchmate..."
echo "Repository location: $SCRIPT_DIR"

# Ensure Claude skills directory exists
mkdir -p "$SKILLS_DIR"

# Symlink all skills
echo ""
echo "Linking Claude Skills..."
for skill in "$SCRIPT_DIR/skills"/*/; do
    if [ -d "$skill" ]; then
        skill_name=$(basename "$skill")

        # Remove existing symlink or directory
        if [ -L "$SKILLS_DIR/$skill_name" ] || [ -d "$SKILLS_DIR/$skill_name" ]; then
            rm -rf "$SKILLS_DIR/$skill_name"
        fi

        ln -s "$skill" "$SKILLS_DIR/$skill_name"
        echo "  Linked: $skill_name"
    fi
done

# Make CLI scripts executable
echo ""
echo "Making scripts executable..."
chmod +x "$SCRIPT_DIR"/*_cli.py 2>/dev/null || true
chmod +x "$SCRIPT_DIR"/*.py 2>/dev/null || true

echo ""
echo "Setup complete!"
echo ""
echo "Available tools:"
echo "  - primer_cli.py      : PCR primer design"
echo "  - protparam_cli.py   : Protein parameter calculation"
echo "  - orf_verifier_cli.py: ORF verification in plasmids"
echo "  - reactor_cli.py     : Reaction buffer calculator"
echo ""
echo "Skills are now available in Claude Code."

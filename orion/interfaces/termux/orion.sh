#!/data/data/com.termux/files/usr/bin/bash
# Termux:Widget shortcut — copy or symlink this file into ~/.shortcuts/ to
# get a one-tap home-screen button that starts a conversation with Orion.
# Termux:Widget labels the button after the destination filename, hence
# copying it to Orion.sh below.
#
#   mkdir -p ~/.shortcuts
#   cp ~/orion/interfaces/termux/orion.sh ~/.shortcuts/Orion.sh
#   chmod +x ~/.shortcuts/Orion.sh
#
# Then add the Termux:Widget widget to your home screen and pick "Orion".
# Adjust ORION_DIR below if you cloned the repo somewhere other than ~/orion.

set -e
ORION_DIR="$HOME/orion"

cd "$ORION_DIR"
source .venv/bin/activate
python -m interfaces.termux.orion_termux

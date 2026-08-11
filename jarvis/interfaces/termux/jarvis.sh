#!/data/data/com.termux/files/usr/bin/bash
# Termux:Widget shortcut — copy or symlink this file into ~/.shortcuts/ to
# get a one-tap home-screen button that starts a conversation with Orion.
# Termux:Widget labels the button after the destination filename, hence
# copying it to Orion.sh below even though the source file here keeps its
# original name.
#
#   mkdir -p ~/.shortcuts
#   cp ~/jarvis/interfaces/termux/jarvis.sh ~/.shortcuts/Orion.sh
#   chmod +x ~/.shortcuts/Orion.sh
#
# Then add the Termux:Widget widget to your home screen and pick "Orion".
# Adjust JARVIS_DIR below if you cloned the repo somewhere other than ~/jarvis.

set -e
JARVIS_DIR="$HOME/jarvis"

cd "$JARVIS_DIR"
source .venv/bin/activate
python -m interfaces.termux.jarvis_termux

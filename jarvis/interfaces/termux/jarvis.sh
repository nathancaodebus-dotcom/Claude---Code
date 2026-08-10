#!/data/data/com.termux/files/usr/bin/bash
# Termux:Widget shortcut — copy or symlink this file into ~/.shortcuts/ to
# get a one-tap home-screen button that starts a conversation with Jarvis.
#
#   mkdir -p ~/.shortcuts
#   cp ~/jarvis/interfaces/termux/jarvis.sh ~/.shortcuts/Jarvis.sh
#   chmod +x ~/.shortcuts/Jarvis.sh
#
# Then add the Termux:Widget widget to your home screen and pick "Jarvis".
# Adjust JARVIS_DIR below if you cloned the repo somewhere other than ~/jarvis.

set -e
JARVIS_DIR="$HOME/jarvis"

cd "$JARVIS_DIR"
source .venv/bin/activate
python -m interfaces.termux.jarvis_termux

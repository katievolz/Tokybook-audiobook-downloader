#!/bin/bash

# Check if Homebrew is installed
if command -v brew &> /dev/null; then
    echo "Homebrew is installed."
else
    echo "Homebrew is NOT installed."
    echo "Install with: curl -fsSL https://raw.githubusercontent.com/Homebrew/install/HEAD/install.sh"
fi

# Check if pip is installed
if command -v pip3 &> /dev/null; then
    echo "pip3 is installed."
else
    echo "pip3 is NOT installed."
    echo "Install with: brew install python3"
fi

pip3 install -r requirements.txt

playwright install

HOMEBREW_NO_AUTO_UPDATE=1 brew install ffmpeg

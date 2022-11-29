#!/bin/bash

# automatic update of VSCode to latest version
# run this when VSCode notifies you of a new version
# NOTE: this script requires sudo privileges
# usage: auto_update_vscode_ubuntu.sh

# get latest version
wget 'https://code.visualstudio.com/sha/download?build=stable&os=linux-deb-x64' -O /tmp/code_latest_amd64.deb
# install latest version
sudo dpkg -i /tmp/code_latest_amd64.deb
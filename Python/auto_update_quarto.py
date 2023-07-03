"""
This script will download and install the latest version of Quarto.
Should work on Ubuntu >18.04.
"""

import os
import time

print("Upgrading Quarto")

# Show the current quarto version
print("Current Quarto version:")
os.system("quarto --version")

# download the latest version of Quarto
os.system("gh --repo quarto-dev/quarto-cli release download --pattern *amd64.deb")
time.sleep(1)

# get the full path of the file that was downloaded
for fname in os.listdir('.'):
    if fname.endswith('amd64.deb'):
        deb_file = os.path.abspath(fname)

# install the latest version of Quarto
os.system(f"sudo dpkg -i {deb_file}")

# remove the .deb file
os.remove(deb_file)

# Show the quarto version
print("New Quarto version:")
os.system("quarto --version")

# Print completion message
print("Quarto upgrade completed")

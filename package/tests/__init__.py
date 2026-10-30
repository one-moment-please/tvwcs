import os
# The tests give Debian's answers on any computer (an Arch CI job included); distro tests ask for Arch themselves.
os.environ["TVWCS_FAMILY"]="debian"

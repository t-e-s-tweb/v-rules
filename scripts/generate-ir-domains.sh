#!/bin/bash

gh release download -p domainspk.txt --repo t-e-s-tweb/v-rules
cat domainspk.txt | grep -Ev ".+\.pk$" | sed '1 a\pk\nxn--mgbai9azgqp6j' | LC_ALL=C sort -u > pk.txt
comm -23 pk.txt ./redundant/redundant-domains.txt > pk-lite.txt
mv pk.txt pk-lite.txt release

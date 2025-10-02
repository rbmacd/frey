#!/bin/bash

### Helper script to stand up netlab in a virtual environment
python3 -m venv ./services/netlab/netlab-venv/
source ./services/netlab/netlab-venv/bin/activate
pip install networklab
netlab install -y ansible
netlab install -y containerlab
netlab install -y grpc
netlab install -y graph
deactivate

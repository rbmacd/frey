#!/bin/bash

# Activate virtual env
source ./bin/activate

# Install pybatfish and supporting libraries
python3 -m pip install --upgrade pip
python3 -m pip install -r ./requirements.txt

# Start the batfish service
docker pull batfish/allinone
docker run --name batfish -v batfish-data:/data -p 8888:8888 -p 9996:9996 batfish/allinone
FROM quay.io/ansible/awx-ee:latest

# Install NetBox collection
RUN ansible-galaxy collection install netbox.netbox

# Install pynetbox Python package
RUN pip3 install --no-cache-dir pynetbox

# Metadata
LABEL name="frey-awx-netbox-ee"
LABEL description="AWX EE with NetBox support"
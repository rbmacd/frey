# S3 Backend for Terraform State
#
# This file defines the backend type only.
# Actual configuration values are in backend.tfvars (git-ignored).
#
# Setup:
#   1. Run ./setup-backend.sh to create S3 bucket and DynamoDB table
#   2. Copy backend.tfvars.example to backend.tfvars
#   3. Update backend.tfvars with your account ID and region
#   4. Initialize: terraform init -backend-config=backend.tfvars
#
# Cost: ~$0.02/month for S3 + DynamoDB

terraform {
  backend "s3" {
    # All values configured via backend.tfvars
    # Run: terraform init -backend-config=backend.tfvars
  }
}
# S3 Backend for Terraform State
#
# This backend configuration stores Terraform state in S3 with the following benefits:
# 1. State survives laptop crashes, terminal closures, or machine switches
# 2. State locking via DynamoDB prevents concurrent modifications
# 3. State versioning allows rollback if state gets corrupted
# 4. Enables destroying infrastructure from any machine with AWS credentials
#
# IMPORTANT: You must create the S3 bucket and DynamoDB table BEFORE running terraform init
# Run the setup-backend.sh script to create these resources automatically
#
# Cost: ~$0.02/month for S3 + DynamoDB (negligible compared to forgetting to destroy infrastructure)
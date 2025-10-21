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

terraform {
  backend "s3" {
    # Replace <ACCOUNT_ID> with your 12-digit AWS account ID
    # Or run: aws sts get-caller-identity --query Account --output text
    bucket = "containerlab-tfstate-<ACCOUNT_ID>"
    
    key    = "infrastructure/terraform.tfstate"
    region = "us-east-1"
    
    # Enable encryption at rest
    encrypt = true
    
    # DynamoDB table for state locking (prevents concurrent modifications)
    dynamodb_table = "containerlab-tfstate-lock"
  }
}

# SETUP INSTRUCTIONS:
#
# 1. Get your AWS account ID:
#    aws sts get-caller-identity --query Account --output text
#
# 2. Replace <ACCOUNT_ID> in the bucket name above
#
# 3. Run the setup script to create S3 bucket and DynamoDB table:
#    ./setup-backend.sh
#
# 4. Initialize Terraform with the backend:
#    terraform init
#
# 5. When prompted to migrate state, answer "yes" if you have existing local state
#
# ALTERNATIVE: Use backend.tfvars for configuration
#
# Instead of hardcoding the bucket name, you can use a backend config file:
#
#   terraform init -backend-config=backend.tfvars
#
# Where backend.tfvars contains:
#   bucket = "containerlab-tfstate-123456789012"
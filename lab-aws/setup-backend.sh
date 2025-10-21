#!/bin/bash
# Terraform S3 Backend Setup Script
# Creates S3 bucket and DynamoDB table for Terraform state management
#
# Usage:
#   chmod +x setup-backend.sh  (first time only)
#   ./setup-backend.sh
#
# What this script does:
#   1. Creates S3 bucket: containerlab-tfstate-<ACCOUNT_ID>
#   2. Enables versioning (for state rollback)
#   3. Enables encryption (AES-256)
#   4. Blocks public access
#   5. Creates DynamoDB table: containerlab-tfstate-lock
#   6. Provides next steps to initialize Terraform
#
# Cost: ~$0.02/month for S3 + DynamoDB

set -e

echo "=== Terraform S3 Backend Setup ==="
echo ""

# Check if AWS CLI is configured
if ! aws sts get-caller-identity &>/dev/null; then
    echo "ERROR: AWS CLI is not configured or credentials are invalid"
    echo "Please run: aws configure"
    exit 1
fi

# Get AWS account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
REGION=${AWS_REGION:-us-east-1}
BUCKET_NAME="containerlab-tfstate-${ACCOUNT_ID}"
DYNAMODB_TABLE="containerlab-tfstate-lock"

echo "AWS Account ID: ${ACCOUNT_ID}"
echo "Region: ${REGION}"
echo "S3 Bucket: ${BUCKET_NAME}"
echo "DynamoDB Table: ${DYNAMODB_TABLE}"
echo ""

# Create S3 bucket
echo "Creating S3 bucket for Terraform state..."
if aws s3api head-bucket --bucket "${BUCKET_NAME}" 2>/dev/null; then
    echo "  ✓ Bucket ${BUCKET_NAME} already exists"
else
    if [ "${REGION}" = "us-east-1" ]; then
        aws s3api create-bucket \
            --bucket "${BUCKET_NAME}" \
            --region "${REGION}"
    else
        aws s3api create-bucket \
            --bucket "${BUCKET_NAME}" \
            --region "${REGION}" \
            --create-bucket-configuration LocationConstraint="${REGION}"
    fi
    echo "  ✓ Created bucket ${BUCKET_NAME}"
fi

# Enable versioning
echo "Enabling versioning..."
aws s3api put-bucket-versioning \
    --bucket "${BUCKET_NAME}" \
    --versioning-configuration Status=Enabled
echo "  ✓ Versioning enabled"

# Enable encryption
echo "Enabling encryption..."
aws s3api put-bucket-encryption \
    --bucket "${BUCKET_NAME}" \
    --server-side-encryption-configuration '{
        "Rules": [{
            "ApplyServerSideEncryptionByDefault": {
                "SSEAlgorithm": "AES256"
            },
            "BucketKeyEnabled": true
        }]
    }'
echo "  ✓ Encryption enabled"

# Block public access
echo "Blocking public access..."
aws s3api put-public-access-block \
    --bucket "${BUCKET_NAME}" \
    --public-access-block-configuration \
        BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true
echo "  ✓ Public access blocked"
echo "  ℹ️  Note: This blocks ANONYMOUS access. You can still access with your AWS credentials!"

# Create DynamoDB table for state locking
echo "Creating DynamoDB table for state locking..."
if aws dynamodb describe-table --table-name "${DYNAMODB_TABLE}" --region "${REGION}" &>/dev/null; then
    echo "  ✓ Table ${DYNAMODB_TABLE} already exists"
else
    aws dynamodb create-table \
        --table-name "${DYNAMODB_TABLE}" \
        --attribute-definitions AttributeName=LockID,AttributeType=S \
        --key-schema AttributeName=LockID,KeyType=HASH \
        --billing-mode PAY_PER_REQUEST \
        --region "${REGION}" \
        --tags Key=Purpose,Value=TerraformStateLock Key=Project,Value=Containerlab \
        > /dev/null
    
    echo "  ✓ Created table ${DYNAMODB_TABLE}"
    echo "  ⏳ Waiting for table to be active..."
    aws dynamodb wait table-exists --table-name "${DYNAMODB_TABLE}" --region "${REGION}"
    echo "  ✓ Table is active"
fi

echo ""
echo "=== Setup Complete! ==="
echo ""
echo "Next steps:"
echo ""
echo "1. Update backend.tf with your bucket name:"
echo "   sed -i 's/<ACCOUNT_ID>/${ACCOUNT_ID}/g' backend.tf"
echo ""
echo "2. Initialize Terraform with the backend:"
echo "   terraform init"
echo ""
echo "3. If you have existing local state, Terraform will ask if you want to migrate it to S3"
echo "   Answer 'yes' to migrate"
echo ""
echo "Monthly cost estimate:"
echo "  - S3 storage: ~$0.01"
echo "  - DynamoDB: ~$0.01"
echo "  - Total: ~$0.02/month"
echo ""
echo "This cost is negligible compared to forgetting to destroy a single r7i.xlarge instance for 1 hour ($0.27)"
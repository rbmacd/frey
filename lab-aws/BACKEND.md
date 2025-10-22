# Terraform S3 Backend Guide

This document explains the S3 backend configuration for managing Terraform state in this containerlab infrastructure project.

## Why S3 Backend for Ephemeral Infrastructure?

You might think: "This is temporary infrastructure, why do I need remote state?" Here's why it matters:

### The Problem: Lost State = Orphaned Resources

```bash
# Common scenario:
terraform apply  # Deploys VPC, EC2, Security Groups
# Infrastructure running: $0.12-0.30/hour

# Your laptop crashes / terminal closes / state file corrupted
# Later...

terraform destroy
# ERROR: No state found
# Infrastructure still running in AWS
# Manual cleanup required or you keep paying
```

### Real Cost Example

**Scenario:** You deploy r7i.xlarge for testing, laptop crashes, lose state

- **Without backend:**
  - Infrastructure runs until you notice (could be days)
  - 24 hours = $2.88 wasted
  - Manual AWS console cleanup (tedious)
  
- **With backend:**
  - State safe in S3
  - `terraform destroy` works from any machine
  - Cost: $0.02/month for peace of mind

**ROI:** Backend pays for itself if it saves you from ONE forgotten instance for just 2 hours.

## What the Backend Provides

### 1. State Persistence

State file survives:
- Laptop crashes
- Terminal closures
- Disk corruption
- Machine switches

### 2. State Locking (via DynamoDB)

Prevents concurrent modifications:
```bash
# Terminal 1
terraform apply  # Acquires lock

# Terminal 2 (you forgot about Terminal 1)
terraform apply  # ERROR: State is locked
# Saved you from corruption!
```

### 3. State Versioning

Every change creates a new version:
```bash
# Accidentally broke something?
aws s3api list-object-versions \
  --bucket containerlab-tfstate-123456789012 \
  --prefix infrastructure/

# Download previous version
aws s3api get-object \
  --version-id <VERSION_ID> \
  --key infrastructure/terraform.tfstate \
  terraform.tfstate.backup
```

### 4. Multi-Machine Access

```bash
# Friday: Deploy from desktop
desktop$ terraform apply

# Weekend: Forgot to destroy

# Monday: Destroy from laptop
laptop$ git clone <repo>
laptop$ terraform init  # Downloads state from S3
laptop$ terraform destroy  # Works perfectly!
```

## Architecture

```
Your Machine                    AWS Account (Default: us-east-2)
    │                               │
    ├─ terraform apply/destroy      │
    │                               │
    ├─ Read/Write State ────────> S3 Bucket
    │                             (containerlab-tfstate-*)
    │                             └─ Versioned
    │                             └─ Encrypted
    │                             └─ Private
    │                               │
    └─ Acquire/Release Lock ────> DynamoDB Table
                                  (containerlab-tfstate-lock)
                                  └─ Prevents concurrent access
```

## Setup Process

### Automated Setup (Recommended)

```bash
# 1. Run setup script
./setup-backend.sh

# 2. Update backend.tf with your account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)
sed -i "s/<ACCOUNT_ID>/${ACCOUNT_ID}/g" backend.tf

# 3. Initialize
terraform init
```

### What setup-backend.sh Does

1. **Creates S3 Bucket**
   - Name: `containerlab-tfstate-<ACCOUNT_ID>`
   - Region: `us-east-1` (or your configured region)
   - Versioning: Enabled
   - Encryption: AES256 (server-side)
   - Public Access: Blocked

2. **Creates DynamoDB Table**
   - Name: `containerlab-tfstate-lock`
   - Primary Key: `LockID` (String)
   - Billing: Pay-per-request (only charges for locks)
   - Purpose: Prevents concurrent state modifications

### Manual Setup (Alternative)

If you prefer to run commands manually:

```bash
# Get account ID
ACCOUNT_ID=$(aws sts get-caller-identity --query Account --output text)

# Set region (default: us-east-2, or use your preferred region)
REGION="us-east-2"

# Create S3 bucket
if [ "${REGION}" = "us-east-1" ]; then
  # us-east-1 doesn't need LocationConstraint
  aws s3api create-bucket \
    --bucket "containerlab-tfstate-${ACCOUNT_ID}" \
    --region "${REGION}"
else
  # Other regions require LocationConstraint
  aws s3api create-bucket \
    --bucket "containerlab-tfstate-${ACCOUNT_ID}" \
    --region "${REGION}" \
    --create-bucket-configuration LocationConstraint="${REGION}"
fi

# Enable versioning
aws s3api put-bucket-versioning \
  --bucket "containerlab-tfstate-${ACCOUNT_ID}" \
  --region "${REGION}" \
  --versioning-configuration Status=Enabled

# Enable encryption
aws s3api put-bucket-encryption \
  --bucket "containerlab-tfstate-${ACCOUNT_ID}" \
  --region "${REGION}" \
  --server-side-encryption-configuration '{
    "Rules": [{
      "ApplyServerSideEncryptionByDefault": {
        "SSEAlgorithm": "AES256"
      },
      "BucketKeyEnabled": true
    }]
  }'

# Block public access
aws s3api put-public-access-block \
  --bucket "containerlab-tfstate-${ACCOUNT_ID}" \
  --region "${REGION}" \
  --public-access-block-configuration \
    BlockPublicAcls=true,IgnorePublicAcls=true,BlockPublicPolicy=true,RestrictPublicBuckets=true

# Create DynamoDB table
aws dynamodb create-table \
  --table-name containerlab-tfstate-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST \
  --region "${REGION}"
```

## Backend Configuration

### backend.tf Structure

```hcl
terraform {
  backend "s3" {
    bucket         = "containerlab-tfstate-<ACCOUNT_ID>"
    key            = "infrastructure/terraform.tfstate"
    region         = "us-east-2"  # Default, change if using different region
    encrypt        = true
    dynamodb_table = "containerlab-tfstate-lock"
  }
}
```

**Key Parameters:**
- `bucket`: Where state is stored (must exist before init)
- `key`: Path within bucket (allows multiple projects)
- `region`: AWS region for S3 and DynamoDB (default: us-east-2)
- `encrypt`: Enable server-side encryption
- `dynamodb_table`: For state locking

**Important:** Backend region should match your `aws_region` variable in terraform.tfvars for consistency.

### Alternative: backend.tfvars

Instead of hardcoding in backend.tf:

```bash
# Create backend.tfvars
cat > backend.tfvars << EOF
bucket         = "containerlab-tfstate-123456789012"
key            = "infrastructure/terraform.tfstate"
region         = "us-east-2"
encrypt        = true
dynamodb_table = "containerlab-tfstate-lock"
EOF

# Initialize with config file
terraform init -backend-config=backend.tfvars
```

**Benefits:**
- Keep backend.tf generic across projects
- Store account-specific config separately
- Easy to use different regions: just change region in backend.tfvars
- backend.tfvars is git-ignored by default

## Usage

### Initial Setup

```bash
# First time setup (uses default us-east-2 region)
./setup-backend.sh

# Or specify a custom region:
# AWS_REGION=us-west-2 ./setup-backend.sh

sed -i "s/<ACCOUNT_ID>/$(aws sts get-caller-identity --query Account --output text)/g" backend.tf

# If using non-default region, update backend.tf:
# sed -i "s/us-east-2/us-west-2/g" backend.tf

terraform init
```

**Important:** Your backend region should match your resource region (aws_region in terraform.tfvars) for consistency.

### Normal Operations

```bash
# Deploy infrastructure
terraform apply
# State is automatically saved to S3
# Lock is acquired during apply, released after

# Destroy infrastructure
terraform destroy
# State is automatically updated in S3
# Lock ensures no concurrent operations
```

### Working Across Machines

```bash
# Machine 1: Deploy
machine1$ terraform apply

# Machine 2: Check what's deployed
machine2$ git clone <repo>
machine2$ terraform init  # Downloads state from S3
machine2$ terraform show  # Shows current infrastructure

# Machine 2: Destroy
machine2$ terraform destroy  # Works because state is in S3
```

## State Management

### View State Versions

```bash
# List all versions
aws s3api list-object-versions \
  --bucket containerlab-tfstate-$(aws sts get-caller-identity --query Account --output text) \
  --prefix infrastructure/terraform.tfstate

# Output includes VersionId for each state version
```

### Restore Previous State

```bash
# Download specific version
aws s3api get-object \
  --bucket containerlab-tfstate-$(aws sts get-caller-identity --query Account --output text) \
  --key infrastructure/terraform.tfstate \
  --version-id <VERSION_ID> \
  terraform.tfstate.backup

# Review before restoring
terraform show terraform.tfstate.backup

# If good, restore
mv terraform.tfstate.backup terraform.tfstate
terraform refresh
```

### Handle Locked State

If state is locked and process died:

```bash
# Get lock ID from error message
terraform force-unlock <LOCK_ID>

# Or manually remove from DynamoDB
aws dynamodb delete-item \
  --table-name containerlab-tfstate-lock \
  --key '{"LockID": {"S": "containerlab-tfstate-<ACCOUNT_ID>/infrastructure/terraform.tfstate"}}'
```

### View Lock Information

```bash
# Check current locks
aws dynamodb scan \
  --table-name containerlab-tfstate-lock \
  --output table

# View lock details
aws dynamodb get-item \
  --table-name containerlab-tfstate-lock \
  --key '{"LockID": {"S": "containerlab-tfstate-<ACCOUNT_ID>/infrastructure/terraform.tfstate"}}'
```

## Cost Analysis

### S3 Costs

```
Storage: 1 MB state file = $0.000023/month
Versioning: Keep 10 versions = $0.00023/month
Requests: 
  - terraform apply: 2 requests (PUT, GET)
  - terraform destroy: 2 requests
  - 20 operations/month = $0.0001
Total S3: ~$0.01/month
```

### DynamoDB Costs

```
Storage: <1 KB lock record = $0.000000025/month
Requests: Pay-per-request
  - Lock acquire: 1 write
  - Lock release: 1 write
  - 20 operations/month = $0.000025
Total DynamoDB: ~$0.01/month
```

### Total Backend Cost: ~$0.02/month

**Compare to forgetting infrastructure:**
- r7i.xlarge: $0.27/hour
- Forget for 2 hours: $0.54 wasted
- Backend pays for itself 27x over

## Security

### IAM Permissions Required

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::containerlab-tfstate-*",
        "arn:aws:s3:::containerlab-tfstate-*/*"
      ]
    },
    {
      "Effect": "Allow",
      "Action": [
        "dynamodb:GetItem",
        "dynamodb:PutItem",
        "dynamodb:DeleteItem"
      ],
      "Resource": "arn:aws:dynamodb:*:*:table/containerlab-tfstate-lock"
    }
  ]
}
```

### Security Features

1. **Encryption at Rest**: AES-256
2. **Encryption in Transit**: TLS (HTTPS)
3. **Public Access Blocked**: Prevents anonymous/unauthenticated access
   - **Important**: This does NOT block you!
   - You access the bucket with your AWS credentials (IAM user/role)
   - Terraform uses your configured AWS credentials to read/write state
   - "Block Public Access" only prevents unauthenticated internet users
4. **Versioning**: Enabled (audit trail)
5. **IAM**: Only authenticated AWS users with proper permissions can access
6. **No Secrets in State**: Use AWS Secrets Manager for sensitive data

### How You Access the Bucket

When Terraform accesses the S3 backend, it uses YOUR AWS credentials:

```bash
# Terraform reads credentials from:
# 1. ~/.aws/credentials (configured via 'aws configure')
# 2. Environment variables (AWS_ACCESS_KEY_ID, AWS_SECRET_ACCESS_KEY)
# 3. IAM role (if running on EC2)
# 4. AWS SSO session

terraform init
# Behind the scenes:
# - Terraform makes AUTHENTICATED request to S3
# - "I am IAM user 'john' with access key AKIA..."
# - AWS checks: "Does user 'john' have s3:GetObject permission for this bucket?"
# - Since you created the bucket, you own it and have full permissions
# - Request allowed ✅

# Public internet user trying to access:
curl https://s3.amazonaws.com/containerlab-tfstate-123/terraform.tfstate
# AWS: "No credentials provided, and public access is blocked"
# Request denied ❌
```

**Key Point:** "Block Public Access" protects against unauthorized access while allowing you (the authenticated bucket owner) full access.

### Access Control Diagram

```
┌─────────────────────────────────────────────────────────────┐
│                    S3 Bucket Access Control                  │
├─────────────────────────────────────────────────────────────┤
│                                                               │
│  Anonymous User (No Credentials)                             │
│  └─> Request to S3                                           │
│       └─> Block Public Access = ❌ DENIED                    │
│                                                               │
│  ─────────────────────────────────────────────────────────  │
│                                                               │
│  You (Authenticated with AWS Credentials)                    │
│  ├─> AWS CLI: aws s3 ls s3://bucket/                         │
│  │    ├─> Reads ~/.aws/credentials                           │
│  │    ├─> Sends: "I am IAM user 'john' (AKIA...)"           │
│  │    ├─> AWS: "User john owns bucket, has full perms"      │
│  │    └─> ✅ ALLOWED                                         │
│  │                                                            │
│  └─> Terraform: terraform init                               │
│       ├─> Reads ~/.aws/credentials                           │
│       ├─> Sends: "I am IAM user 'john' (AKIA...)"           │
│       ├─> AWS: "User john owns bucket, has full perms"      │
│       └─> ✅ ALLOWED                                         │
│                                                               │
│  Block Public Access does NOT affect authenticated requests  │
└─────────────────────────────────────────────────────────────┘
```

### State File Contains

State file includes:
- Resource IDs (EC2 instance IDs, VPC IDs, etc.)
- IP addresses
- Resource attributes
- **Does NOT contain:** SSH private keys, passwords (if configured correctly)

**Best Practice:** Never commit state files to git, even encrypted repos.

## Troubleshooting

### Backend Bucket Doesn't Exist

```bash
# Error: "bucket does not exist"
./setup-backend.sh

# Or create manually
aws s3api create-bucket \
  --bucket containerlab-tfstate-$(aws sts get-caller-identity --query Account --output text) \
  --region us-east-1
```

### DynamoDB Table Doesn't Exist

```bash
# Error: "table does not exist"
aws dynamodb create-table \
  --table-name containerlab-tfstate-lock \
  --attribute-definitions AttributeName=LockID,AttributeType=S \
  --key-schema AttributeName=LockID,KeyType=HASH \
  --billing-mode PAY_PER_REQUEST
```

### Migrate Local State to S3

```bash
# With existing local state
terraform init  # Will prompt to migrate
# Answer "yes" to copy state to S3

# Verify migration
aws s3 ls s3://containerlab-tfstate-$(aws sts get-caller-identity --query Account --output text)/infrastructure/

# Old local state becomes backup
ls -la terraform.tfstate*
```

### Access Denied Errors

**Understanding the Error:**

If you get "Access Denied" when running `terraform init` or `terraform apply`, it's usually one of these issues:

**1. AWS Credentials Not Configured**
```bash
# Check if credentials are configured
aws sts get-caller-identity

# If error, configure credentials:
aws configure
# Enter your Access Key ID and Secret Access Key
```

**2. Using Wrong AWS Profile**
```bash
# Check current profile
echo $AWS_PROFILE

# Set correct profile
export AWS_PROFILE=your-profile-name

# Or specify in Terraform command
AWS_PROFILE=your-profile-name terraform init
```

**3. IAM User Lacks S3 Permissions**
```bash
# Test S3 access
aws s3 ls s3://containerlab-tfstate-$(aws sts get-caller-identity --query Account --output text)

# If access denied, you need these permissions:
# - s3:ListBucket
# - s3:GetObject
# - s3:PutObject
# - s3:DeleteObject

# Your IAM user needs a policy like:
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:GetObject",
        "s3:PutObject",
        "s3:DeleteObject"
      ],
      "Resource": [
        "arn:aws:s3:::containerlab-tfstate-*",
        "arn:aws:s3:::containerlab-tfstate-*/*"
      ]
    }
  ]
}
```

**4. Bucket Doesn't Exist or Wrong Name**
```bash
# List all your S3 buckets
aws s3 ls | grep containerlab

# Check backend.tf has correct bucket name
cat backend.tf | grep bucket

# Verify bucket exists
aws s3api head-bucket --bucket containerlab-tfstate-$(aws sts get-caller-identity --query Account --output text)
```

**5. Region Mismatch**
```bash
# Backend and bucket must be in same region
# Check bucket region
aws s3api get-bucket-location --bucket containerlab-tfstate-$(aws sts get-caller-identity --query Account --output text)

# Check backend.tf has correct region
cat backend.tf | grep region
```

**Important Note About "Block Public Access":**

If you see "Access Denied" and think it's because public access is blocked: **No!**

```bash
# ❌ Common misconception:
"Public access is blocked, so I can't access the bucket"

# ✅ Reality:
# - Public access blocking prevents ANONYMOUS users
# - You access with AWS credentials (authenticated)
# - Authenticated access is NOT affected by public access blocking
# - If you get "Access Denied", it's an IAM permissions issue, not public access blocking
```

**Verify Your Access:**
```bash
# Test authenticated access
aws s3 ls s3://containerlab-tfstate-$(aws sts get-caller-identity --query Account --output text)/

# This should work if:
# ✅ Your credentials are configured
# ✅ Your IAM user has s3:ListBucket permission
# ✅ The bucket exists

# This does NOT require disabling "Block Public Access"
```

**If Still Having Issues:**
```bash
# 1. Verify you're the bucket owner
aws s3api get-bucket-acl --bucket containerlab-tfstate-$(aws sts get-caller-identity --query Account --output text)

# 2. Check bucket policy (should be empty/default)
aws s3api get-bucket-policy --bucket containerlab-tfstate-$(aws sts get-caller-identity --query Account --output text)

# 3. Verify encryption settings
aws s3api get-bucket-encryption --bucket containerlab-tfstate-$(aws sts get-caller-identity --query Account --output text)
```

## Cleanup

When you're completely done with the project:

```bash
# 1. Destroy all infrastructure first
terraform destroy

# 2. Delete state from S3
aws s3 rm s3://containerlab-tfstate-$(aws sts get-caller-identity --query Account --output text)/infrastructure/ --recursive

# 3. Delete all versions (if bucket versioning was on)
aws s3api delete-bucket \
  --bucket containerlab-tfstate-$(aws sts get-caller-identity --query Account --output text)

# 4. Delete DynamoDB table
aws dynamodb delete-table --table-name containerlab-tfstate-lock
```

## Best Practices

1. **Always Setup Backend First** - Before any terraform apply
2. **Don't Skip It** - The $0.02/month is worth it
3. **Use Versioning** - Enabled by default in our setup
4. **Encrypt Everything** - Enabled by default in our setup
5. **Block Public Access** - Enabled by default in our setup
6. **Regular Cleanup** - Don't leave destroyed infrastructure's state around
7. **Document Account ID** - Team members need to know the bucket name
8. **Match Regions** - Backend region should match resource region (aws_region)
9. **Test Backend Access** - Run `terraform init` to verify before deploying resources

## Region Considerations

### Choosing a Backend Region

**Default:** us-east-2 (Ohio) - Good balance of cost and reliability

**Factors to Consider:**
- **Match Resource Region**: Backend and resources should be in same region
- **Latency**: Minimal impact (state is only read/written during terraform operations)
- **Cost**: S3 and DynamoDB costs are similar across regions (~$0.02/month)
- **Compliance**: Some organizations require data residency in specific regions

### Using a Different Region

```bash
# Method 1: Set environment variable before running setup
AWS_REGION=eu-west-1 ./setup-backend.sh

# Method 2: Set AWS_REGION in your shell
export AWS_REGION=eu-west-1
./setup-backend.sh

# Then update backend.tf to match
sed -i 's/us-east-2/eu-west-1/g' backend.tf

# And terraform.tfvars
# aws_region = "eu-west-1"
```

### Multi-Region Considerations

If you're deploying resources in multiple regions, you have two options:

**Option 1: Single Backend for All Regions (Recommended)**
```hcl
# backend.tf - Keep in one region
region = "us-east-2"  # Backend location

# terraform.tfvars - Can be any region
aws_region = "eu-west-1"  # Resource location

# This works fine! State can be in a different region than resources.
```

**Option 2: Separate Backends Per Region**
```hcl
# For us-east-2 deployment
terraform {
  backend "s3" {
    bucket = "containerlab-tfstate-123456789012"
    key    = "us-east-2/terraform.tfstate"
    region = "us-east-2"
  }
}

# For eu-west-1 deployment
terraform {
  backend "s3" {
    bucket = "containerlab-tfstate-123456789012"
    key    = "eu-west-1/terraform.tfstate"
    region = "us-east-2"  # Can use same backend region
  }
}
```

## Summary

**TL;DR:**
- ✅ Run `./setup-backend.sh` once
- ✅ Costs $0.02/month
- ✅ Prevents orphaned resources
- ✅ Enables destroy from any machine
- ✅ Protects against state loss
- ✅ Worth it for peace of mind
- ✅ "Block Public Access" doesn't block you (you're authenticated)

The backend is set-it-and-forget-it infrastructure that makes your ephemeral infrastructure truly manageable.

## FAQ

### Q: If public access is blocked, how can I access the bucket?

**A:** "Block Public Access" only blocks **anonymous/unauthenticated** users. You access the bucket with your AWS credentials (IAM user/role), which is authenticated access.

```bash
# When you run Terraform:
terraform init

# Behind the scenes:
# 1. Terraform reads ~/.aws/credentials
# 2. Makes AUTHENTICATED request: "I am user X with credentials Y"
# 3. AWS: "User X owns this bucket, access granted"
# 4. Success ✅

# When anonymous user tries:
curl https://s3.amazonaws.com/your-bucket/file
# AWS: "No credentials, public access blocked"
# Denied ❌
```

**Think of it like a locked door:**
- "Block Public Access" = Door is locked to strangers
- Your AWS credentials = You have the key
- You can still open the door with your key!

### Q: Do I need to disable public access blocking to use Terraform?

**A:** No! Never disable public access blocking. Terraform works perfectly with it enabled because Terraform uses your authenticated AWS credentials.

### Q: What if I get "Access Denied" with the backend?

**A:** This is an IAM permissions issue, NOT a public access issue. Check:
1. Are your AWS credentials configured? (`aws sts get-caller-identity`)
2. Does your IAM user have S3 permissions? (ListBucket, GetObject, PutObject)
3. Are you using the correct AWS profile?

See the [Access Denied Errors](#access-denied-errors) section above for detailed troubleshooting.

### Q: Is the backend necessary for temporary infrastructure?

**A:** Highly recommended! If you forget to destroy infrastructure and lose your state file, you'll need to manually clean up AWS resources. The backend costs $0.02/month and pays for itself if it saves you from forgetting a single r7i.xlarge instance for just 2 hours ($0.54).

### Q: Can I use the backend with multiple team members?

**A:** Yes! Each team member needs:
1. AWS credentials with access to the S3 bucket and DynamoDB table
2. The same backend configuration (bucket name, region)
3. Git clone of the repository

The DynamoDB lock prevents concurrent modifications automatically.

### Q: How do I backup my state?

**A:** State is automatically backed up through S3 versioning (enabled by default). Every change creates a new version. You can list and restore previous versions using AWS CLI:

```bash
# List versions
aws s3api list-object-versions \
  --bucket containerlab-tfstate-<ACCOUNT_ID> \
  --prefix infrastructure/

# Restore specific version
aws s3api get-object \
  --version-id <VERSION_ID> \
  --key infrastructure/terraform.tfstate \
  terraform.tfstate.backup
```
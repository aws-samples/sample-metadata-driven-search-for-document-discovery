# Metadata-Driven Search for Document Discovery

This CDK project deploys a Bedrock Knowledge Base with OpenSearch Serverless for intelligent document search and retrieval using metadata-driven filtering.

## Architecture Overview
![Architecture Diagram](/resources/MetadataDrivenSearchDocDiscovery.png)

The solution consists of four CDK stacks that deploy:

- **DataStack**: S3 buckets, IAM roles, and Lambda function for metadata processing
- **IndexStack**: Vector search infrastructure with collection and index
- **BedrockStack**: Knowledge Base with custom document parsing and transformations
- **AppInfraStack**: Application infrastructure for the Streamlit search interface

## Prerequisites

### AWS Account Setup
- AWS CLI configured with appropriate permissions
- CDK v2 installed (`npm install -g aws-cdk`)
- Python 3.8+ with pip
- Access to Amazon Bedrock models (Claude 3 Haiku, Titan Embed v2)

### CDK Bootstrap Requirements
Before deploying, add this inline policy to your CDK CloudFormation execution role (typically `cdk-{qualifier}-cfn-exec-role-{account}-{region}`):

```json
{
    "Version": "2012-10-17",
    "Statement": [
        {
            "Action": "aoss:APIAccessAll",
            "Effect": "Allow",
            "Resource": "*"
        }
    ]
}
```

## Deployment Instructions

### 1. Clone and Configure
```bash
git clone <repository-url>
cd metadata-driven-search-for-document-discovery
```

### 2. Install Dependencies
```bash
python -m venv .venv
source .venv/bin/activate  # On Windows: .venv\Scripts\activate
pip install -r requirements.txt
```

### 3. Deploy Infrastructure
```bash
# Bootstrap CDK (if not done previously)
cdk bootstrap

# Deploy all stacks in order
cdk deploy --all
```

The stacks will deploy with proper dependencies automatically.

### 4. Upload Documents
After deployment, upload your documents to the Knowledge Base S3 bucket:
```bash
aws s3 cp your-documents/ s3://my-kb-docs-bucket-{ACCOUNT_ID}/ --recursive
```

### 5. Sync Knowledge Base
1. Go to AWS Console → Bedrock → Knowledge Bases
2. Find your knowledge base (`my-test-kb`)
3. Select the data source and click **Sync**
4. Wait for ingestion to complete

### 6. Access Search Application
The Streamlit search application is automatically deployed and running on EC2 via the AppInfraStack.

1. Go to AWS Console → CloudFormation → Stacks
2. Find the **AppInfraStack** stack
3. Go to the **Outputs** tab
4. Click on the **ApplicationURL** value to access the search interface

The application will be available at the Application Load Balancer URL (e.g., `http://your-alb-dns-name.us-east-1.elb.amazonaws.com`)

## Key Features

### Document Processing
- **Custom Parsing**: Uses Claude 3 Haiku with specialized prompt for legal documents
- **Metadata Extraction**: Automatically extracts company names, dates, breach requirements
- **Lambda Transformation**: Post-processing for metadata enrichment

### Search Capabilities
- **Natural Language Queries**: Convert plain English to OpenSearch DQL
- **Metadata Filtering**: Search by breach notifications, time requirements, expense types
- **Company Aggregation**: Results grouped by client companies

### Example Queries
- "What are the breach notification requirements for each client?"
- "Show me time entry requirements"
- "What types of expenses are billable?"

## Configuration Options

### Embedding Models
Available in `config.py`:
- `amazon.titan-embed-text-v1` (1536 dimensions)
- `amazon.titan-embed-text-v2:0` (1024 dimensions) - **Default**
- `cohere.embed-english-v3` (1024 dimensions)

### Chunking Strategies
- **Default chunking**: Bedrock automatic
- **Fixed-size chunking**: 2000 tokens, 10% overlap - **Default**
- **No chunking**: Process entire documents

## Testing Recommendations

**⚠️ Important: Use Non-Production Data Only**

This solution is designed for demonstration and testing purposes. Always use non-production, synthetic, or publicly available data when testing:

- **Do not upload sensitive or confidential documents**
- **Use sample legal documents or create mock data for testing**
- **Ensure compliance with your organization's data governance policies**
- **Consider using anonymized or redacted versions of real documents**

For production deployments, implement additional security controls, data classification, and access management appropriate for your sensitive data.

## Cleanup and Destroy

To avoid unnecessary costs, remove all resources when testing is complete.

### 1. Empty S3 Buckets
Before destroying the stacks, you must empty the S3 buckets:
```bash
# Empty the knowledge base documents bucket
aws s3 rm s3://my-kb-meta-bucket-{ACCOUNT_ID}/ --recursive
aws s3 rm s3://my-kb-docs-bucket-{ACCOUNT_ID}/ --recursive
```

### 2. Delete Lambda Log Group
```bash
# Delete the Lambda function log group
aws logs delete-log-group --log-group-name /aws/lambda/demo-metadata-processing
```

### 3. Destroy all stacks
```bash
# Destroy all stacks
cdk destroy --all
```

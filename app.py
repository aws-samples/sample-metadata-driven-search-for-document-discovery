#!/usr/bin/env python3
import aws_cdk as cdk
from stacks.root_stack import RootStack
from stacks.oss_infra_stack import OpenSearchServerlessStack
from stacks.kb_infra_stack import BedrockKBStack
from stacks.app_infra_stack import AppInfraStack

app = cdk.App()

# Step 1: Deploy RootStack first
root_stack = RootStack(app, "DataStack",
    knowledge_base_bucket_name="my-kb-docs-bucket",
    knowledge_base_metadata_bucket_name="my-kb-meta-bucket",
)

# Step 2: Deploy OpenSearch Serverless stack
oss_stack = OpenSearchServerlessStack(app, "IndexStack")
oss_stack.add_dependency(root_stack)  # Make sure root stack is deployed first

# Step 3: Deploy Bedrock KB stack that depends on both previous stacks
kb_stack = BedrockKBStack(app, "BedrockStack",
    knowledge_base_bucket_arn=root_stack.knowledge_base_bucket.bucket_arn,
    metadata_bucket_arn=root_stack.metadata_bucket.bucket_arn,
    lambda_function_arn=root_stack.lambda_fn.function_arn
)
kb_stack.add_dependency(root_stack)  # Explicit dependency on root stack
kb_stack.add_dependency(oss_stack)   # Explicit dependency on OpenSearch stack

#Deploy the Application Infrastructure Stack
app_stack = AppInfraStack(app, "AppInfraStack")
app_stack.add_dependency(root_stack)  
app_stack.add_dependency(oss_stack)

app.synth()
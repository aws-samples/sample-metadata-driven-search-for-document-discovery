from aws_cdk import (
    Stack,
    Duration,
    CfnOutput,
    Aws,
    aws_s3 as s3,
    aws_iam as iam,
    aws_lambda as _lambda,
    aws_ssm as ssm
)
from constructs import Construct

class RootStack(Stack):
    def __init__(self, scope: Construct, id: str,
                 knowledge_base_bucket_name: str,
                 knowledge_base_metadata_bucket_name: str,
                 **kwargs):
        super().__init__(scope, id, **kwargs)

        # --- S3 Buckets ---
        self.knowledge_base_bucket = s3.Bucket(self, "KnowledgeBaseBucket",
            bucket_name=f"{knowledge_base_bucket_name}-{Aws.ACCOUNT_ID}"
        )

        self.metadata_bucket = s3.Bucket(self, "KnowledgeBaseMetaDataBucket",
            bucket_name=f"{knowledge_base_metadata_bucket_name}-{Aws.ACCOUNT_ID}"
        )

        # --- Bedrock IAM Role ---
        self.bedrock_role = iam.Role(self, "BedrockKnowledgeBaseRole",
            role_name="bedrock-execution-role-for-kb",
            assumed_by=iam.ServicePrincipal("bedrock.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonOpenSearchServiceFullAccess")
            ],
            inline_policies={
                "BedrockKBCustomPolicy": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        sid="BedrockInvokeModelStatement",
                        actions=["bedrock:InvokeModel"],
                        effect=iam.Effect.ALLOW,
                        resources=[
                            f"arn:aws:bedrock:{Aws.REGION}::foundation-model/anthropic.claude-3-haiku-20240307-v1:0",
                            f"arn:aws:bedrock:{Aws.REGION}::foundation-model/amazon.titan-embed-text-v2:0"
                        ]
                    ),
                    iam.PolicyStatement(
                        sid="LambdaInvokeFunctionStatement",
                        actions=["lambda:InvokeFunction"],
                        effect=iam.Effect.ALLOW,
                        resources=[
                            f"arn:aws:lambda:{Aws.REGION}:{Aws.ACCOUNT_ID}:function:demo-metadata-processing:*"
                        ],
                        conditions={
                            "StringEquals": {
                                "aws:ResourceAccount": Aws.ACCOUNT_ID
                            }
                        }
                    ),
                    iam.PolicyStatement(
                        sid="OpenSearchServerlessAPIAccessAllStatement",
                        actions=["aoss:APIAccessAll"],
                        effect=iam.Effect.ALLOW,
                        resources=[
                            f"arn:aws:aoss:{Aws.REGION}:{Aws.ACCOUNT_ID}:collection/*"
                        ]
                    ),
                    iam.PolicyStatement(
                        sid="S3ListBucketStatement",
                        actions=["s3:ListBucket"],
                        effect=iam.Effect.ALLOW,
                        resources=[self.knowledge_base_bucket.bucket_arn],
                        conditions={
                            "StringEquals": {
                                "aws:ResourceAccount": Aws.ACCOUNT_ID
                            }
                        }
                    ),
                    iam.PolicyStatement(
                        sid="S3GetObjectStatement",
                        actions=["s3:GetObject"],
                        effect=iam.Effect.ALLOW,
                        resources=[
                            self.knowledge_base_bucket.bucket_arn,
                            f"{self.metadata_bucket.bucket_arn}/*",
                            f"{self.knowledge_base_bucket.bucket_arn}/*"
                        ],
                        conditions={
                            "StringEquals": {
                                "aws:ResourceAccount": Aws.ACCOUNT_ID
                            }
                        }
                    ),
                    iam.PolicyStatement(
                        sid="S3PutObjectStatement",
                        actions=["s3:PutObject"],
                        effect=iam.Effect.ALLOW,
                        resources=[
                            f"{self.metadata_bucket.bucket_arn}/*"
                        ],
                        conditions={
                            "StringEquals": {
                                "aws:ResourceAccount": Aws.ACCOUNT_ID
                            }
                        }
                    )
                ])
            }
        )

        ssm.StringParameter(self, "BedrockKBRoleArnParam",
            parameter_name="/kb/bedrockExecutionRoleArn",
            string_value=self.bedrock_role.role_arn
        )

        # --- EC2 IAM Role ---
        self.ec2_role = iam.Role(self, "AnycompanyDemoEC2Role",
            role_name="anycompany-demo-ec2",
            assumed_by=iam.ServicePrincipal("ec2.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonBedrockFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonOpenSearchServiceFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonSSMManagedInstanceCore")
            ],
            inline_policies={
                "anycompany-aoss-api-inline-policy": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        sid="VisualEditor0",
                        effect=iam.Effect.ALLOW,
                        actions=["aoss:APIAccessAll"],
                        resources=["*"]
                    )
                ]),
                "SSMReadPolicy": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        effect=iam.Effect.ALLOW,
                        actions=[
                            "ssm:GetParameter",
                            "ssm:GetParameters"
                        ],
                        resources=[
                            f"arn:aws:ssm:{Aws.REGION}:{Aws.ACCOUNT_ID}:parameter/kb/*"
                        ]
                    )
                ])
            }
        )

        # Store EC2 role ARN in SSM
        ssm.StringParameter(self, "EC2RoleArnParam",
            parameter_name="/app/ec2RoleArn",
            string_value=self.ec2_role.role_arn
        )


        # --- Lambda IAM Role ---
        lambda_role = iam.Role(self, "LambdaFunctionRole",
            assumed_by=iam.ServicePrincipal("lambda.amazonaws.com"),
            managed_policies=[
                iam.ManagedPolicy.from_aws_managed_policy_name("service-role/AWSLambdaBasicExecutionRole"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonBedrockFullAccess"),
                iam.ManagedPolicy.from_aws_managed_policy_name("AmazonS3FullAccess")
            ],
            inline_policies={
                "AppendToLogsPolicy": iam.PolicyDocument(statements=[
                    iam.PolicyStatement(
                        actions=[
                            "logs:CreateLogGroup",
                            "logs:CreateLogStream",
                            "logs:PutLogEvents"
                        ],
                        effect=iam.Effect.ALLOW,
                        resources=["*"]
                    )
                ])
            }
        )

        # --- Lambda Function (from local source) ---
        self.lambda_fn = _lambda.Function(self, "MetadataProcessingLambda",
            function_name="demo-metadata-processing",
            runtime=_lambda.Runtime.PYTHON_3_13,
            handler="main.handler",
            memory_size=1024,
            timeout=Duration.seconds(900),
            role=lambda_role,
            code=_lambda.Code.from_asset("lambda")
        )

        # --- CFN Outputs ---
        CfnOutput(
            self, "KnowledgeBaseBucketName",
            value=self.knowledge_base_bucket.bucket_name,
            description="Name of the S3 bucket storing knowledge base documents"
        )
        
        CfnOutput(
            self, "KnowledgeBaseBucketArn",
            value=self.knowledge_base_bucket.bucket_arn,
            description="ARN of the S3 bucket storing knowledge base documents"
        )
        
        CfnOutput(
            self, "MetadataBucketName",
            value=self.metadata_bucket.bucket_name,
            description="Name of the S3 bucket storing processed metadata"
        )
        
        CfnOutput(
            self, "MetadataBucketArn",
            value=self.metadata_bucket.bucket_arn,
            description="ARN of the S3 bucket storing processed metadata"
        )
        
        CfnOutput(
            self, "BedrockExecutionRoleArn",
            value=self.bedrock_role.role_arn,
            description="ARN of the IAM role used by Bedrock Knowledge Base"
        )
        
        CfnOutput(
            self, "EC2RoleArn",
            value=self.ec2_role.role_arn,
            description="ARN of the IAM role for EC2 instances accessing the search system"
        )
        
        CfnOutput(
            self, "MetadataProcessingLambdaArn",
            value=self.lambda_fn.function_arn,
            description="ARN of the Lambda function that processes document metadata"
        )
        
        CfnOutput(
            self, "MetadataProcessingLambdaName",
            value=self.lambda_fn.function_name,
            description="Name of the Lambda function that processes document metadata"
        )

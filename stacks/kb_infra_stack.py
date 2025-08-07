from constructs import Construct
from aws_cdk import (
    Stack,
    Aws,
    aws_ssm as ssm,
    Fn,
    aws_bedrock as bedrock,
    CfnOutput
)

class BedrockKBStack(Stack):

    def __init__(self, scope: Construct, construct_id: str,
                 knowledge_base_bucket_arn: str,
                 metadata_bucket_arn: str,
                 lambda_function_arn: str,
                 **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # Embedding model
        embedding_model_id = "arn:aws:bedrock:us-east-1::foundation-model/amazon.titan-embed-text-v2:0"

        #Foundation model as parser
        parsing_model_id = "arn:aws:bedrock:us-east-1::foundation-model/anthropic.claude-3-haiku-20240307-v1:0"

        # Load collection and index from SSM
        collection_arn = ssm.StringParameter.value_for_string_parameter(
            self, "/kb/collectionArn"
        )
        vector_index_name = ssm.StringParameter.value_for_string_parameter(
            self, "/kb/indexName"
        )

        # Existing execution role
        kb_role_arn = f"arn:aws:iam::{self.account}:role/bedrock-execution-role-for-kb"

        # Reads parsing prompt
        with open("prompts/parsing_prompt.txt", "r") as f:
            parsing_prompt = f.read()


        # Minimal KB Definition
        knowledge_base = bedrock.CfnKnowledgeBase(self, "BedrockKnowledgeBase",
            name="my-test-kb",
            role_arn=kb_role_arn,
            knowledge_base_configuration=bedrock.CfnKnowledgeBase.KnowledgeBaseConfigurationProperty(
                type="VECTOR",
                vector_knowledge_base_configuration=bedrock.CfnKnowledgeBase.VectorKnowledgeBaseConfigurationProperty(
                    embedding_model_arn=embedding_model_id
                )
            ),
            storage_configuration=bedrock.CfnKnowledgeBase.StorageConfigurationProperty(
                type="OPENSEARCH_SERVERLESS",
                opensearch_serverless_configuration=bedrock.CfnKnowledgeBase.OpenSearchServerlessConfigurationProperty(
                    collection_arn=collection_arn,
                    vector_index_name=vector_index_name,
                    field_mapping=bedrock.CfnKnowledgeBase.OpenSearchServerlessFieldMappingProperty(
                        metadata_field="AMAZON_BEDROCK_METADATA",
                        text_field="AMAZON_BEDROCK_TEXT",
                        vector_field="bedrock-knowledge-base-default-vector"
                    )
                )
            )
        )

        
        data_source = bedrock.CfnDataSource(self, "S3DataSource",
            name="kb-data-source",
            description="Data source for knowledge base",
            knowledge_base_id=knowledge_base.attr_knowledge_base_id,
            data_deletion_policy="RETAIN",
            data_source_configuration={
                "type": "S3",
                "s3Configuration": {
                    "bucketArn": knowledge_base_bucket_arn,
                }
            },
            vector_ingestion_configuration={
                "chunkingConfiguration": {
                    "chunkingStrategy": "FIXED_SIZE",
                    "fixedSizeChunkingConfiguration": {
                        "maxTokens": 2000,
                        "overlapPercentage": 10
                    }
                },
                "parsingConfiguration": {
                    "parsingStrategy": "BEDROCK_FOUNDATION_MODEL",
                    "bedrockFoundationModelConfiguration": {
                        "modelArn": parsing_model_id,
                        "parserMode": "DOCUMENT",
                        "parsingPrompt": {
                            "parsingPromptText": parsing_prompt
                        }
                    }
                },
                "documentEnrichmentConfiguration": {
                    "headerEnrichment": {
                        "enabled": True
                    }
                },
                "customTransformationConfiguration": bedrock.CfnDataSource.CustomTransformationConfigurationProperty(
                    intermediate_storage=bedrock.CfnDataSource.IntermediateStorageProperty(
                        s3_location=bedrock.CfnDataSource.S3LocationProperty(
                            uri=f"s3://{Fn.select(5, Fn.split(':', metadata_bucket_arn))}/"
                        )
                    ),
                    transformations=[bedrock.CfnDataSource.TransformationProperty(
                        step_to_apply="POST_CHUNKING",  # or "POST_EXTRACTION" depending on when you want the transformation to occur
                        transformation_function=bedrock.CfnDataSource.TransformationFunctionProperty(
                            transformation_lambda_configuration=bedrock.CfnDataSource.TransformationLambdaConfigurationProperty(
                                lambda_arn= lambda_function_arn
                            )
                        )
                    )]
                )
            }
        )

        # --- CFN Outputs ---
        CfnOutput(
            self, "KnowledgeBaseId",
            value=knowledge_base.attr_knowledge_base_id,
            description="The ID of the Bedrock Knowledge Base"
        )

        CfnOutput(
            self, "DataSourceId",
            value=data_source.attr_data_source_id,
            description="The ID of the Bedrock Knowledge Base Data Source"
        )
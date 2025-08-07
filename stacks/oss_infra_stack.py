from constructs import Construct
from aws_cdk import (
    Stack,
    Aws,
    aws_ssm as ssm,
    Fn,
    custom_resources as cr,
    aws_opensearchserverless as aoss,
    CfnOutput
)
import json


class OpenSearchServerlessStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        self.collection_name = "kb-vector-collection"
        self.index_name = "bedrock-knowledge-base-default-index"

        # Create resources
        self.encryption_policy = self.create_encryption_policy()
        self.network_policy = self.create_network_policy()
        self.collection = self.create_collection()

        self.network_policy.node.add_dependency(self.encryption_policy)
        self.collection.node.add_dependency(self.network_policy)

        self.data_access_policy = self.create_data_access_policy()
        self.data_access_policy.node.add_dependency(self.collection)

        # Store collection ARN in SSM
        ssm.StringParameter(self, "CollectionArnParam",
            parameter_name="/kb/collectionArn",
            string_value=self.collection.attr_arn
        )

        # Create bare-bones foundational index
        self.create_index()

    def create_encryption_policy(self):
        return aoss.CfnSecurityPolicy(self, "EncryptionPolicy",
            name=f"{self.collection_name}-enc",
            type="encryption",
            policy=json.dumps({
                "Rules": [{
                    "ResourceType": "collection",
                    "Resource": [f"collection/{self.collection_name}"]
                }],
                "AWSOwnedKey": True
            })
        )

    def create_network_policy(self):
        return aoss.CfnSecurityPolicy(self, "NetworkPolicy",
            name=f"{self.collection_name}-net",
            type="network",
            policy=json.dumps([{
                "Rules": [
                    {"ResourceType": "collection", "Resource": [f"collection/{self.collection_name}"]},
                    {"ResourceType": "dashboard", "Resource": [f"collection/{self.collection_name}"]}
                ],
                "AllowFromPublic": True
            }])
        )

    def create_collection(self):
        return aoss.CfnCollection(self, "BasicVectorCollection",
            name=self.collection_name,
            type="VECTORSEARCH"
        )

    def create_data_access_policy(self):
        kb_role_arn = ssm.StringParameter.from_string_parameter_attributes(
            self,
            "BedrockKBRoleArn",
            parameter_name="/kb/bedrockExecutionRoleArn"
        ).string_value

        ec2_role_arn = ssm.StringParameter.from_string_parameter_attributes(
        self,
        "EC2RoleArn",
        parameter_name="/app/ec2RoleArn"
        ).string_value

        return aoss.CfnAccessPolicy(self, "DataAccessPolicy",
            name=f"{self.collection_name}-access",
            type="data",
            policy=json.dumps([{
                "Rules": [
                    {
                        "ResourceType": "collection",
                        "Resource": [f"collection/{self.collection_name}"],
                        "Permission": [
                            "aoss:CreateCollectionItems",
                            "aoss:DeleteCollectionItems",
                            "aoss:UpdateCollectionItems",
                            "aoss:DescribeCollectionItems",
                            "aoss:*"
                        ]
                    },
                    {
                        "ResourceType": "index",
                        "Resource": [f"index/{self.collection_name}/*"],
                        "Permission": [
                            "aoss:ReadDocument",
                            "aoss:WriteDocument",
                            "aoss:CreateIndex",
                            "aoss:DeleteIndex",
                            "aoss:UpdateIndex",
                            "aoss:DescribeIndex",
                            "aoss:*"
                        ]
                    }
                ],
                "Principal": [
                    kb_role_arn,
                    f"arn:aws:iam::{Aws.ACCOUNT_ID}:root",
                    ec2_role_arn 
                ]
            }])
        )

    def create_index(self):
        # Wait for the collection to exist
        wait_for_collection = cr.AwsCustomResource(self, "WaitForCollection",
            on_create=cr.AwsSdkCall(
                service="OpenSearchServerless",
                action="listCollections",
                parameters={},
                physical_resource_id=cr.PhysicalResourceId.of("WaitForCollection")
            ),
            policy=cr.AwsCustomResourcePolicy.from_sdk_calls(
                resources=cr.AwsCustomResourcePolicy.ANY_RESOURCE
            )
        )
        wait_for_collection.node.add_dependency(self.collection)
        wait_for_collection.node.add_dependency(self.data_access_policy)

        index = aoss.CfnIndex(self, "FoundationalVectorIndex",
            collection_endpoint=self.collection.attr_collection_endpoint,
            index_name=self.index_name,
            mappings=aoss.CfnIndex.MappingsProperty(
                properties={
                    "bedrock-knowledge-base-default-vector": aoss.CfnIndex.PropertyMappingProperty(
                        type="knn_vector",
                        dimension=1024,
                        method=aoss.CfnIndex.MethodProperty(
                            engine="faiss",
                            name="hnsw",
                            space_type="l2",  # Euclidean
                            parameters=aoss.CfnIndex.ParametersProperty(
                                ef_construction=512,
                                m=16
                            )
                        )
                    ),
                    "AMAZON_BEDROCK_METADATA": aoss.CfnIndex.PropertyMappingProperty(
                        type="text",
                        index=False
                    ),
                    "AMAZON_BEDROCK_TEXT_CHUNK": aoss.CfnIndex.PropertyMappingProperty(
                        type="text",
                        index=True
                    )
                }
            ),
            settings=aoss.CfnIndex.IndexSettingsProperty(
                index=aoss.CfnIndex.IndexProperty(
                    knn=True,
                    knn_algo_param_ef_search=512,  # You can include this or leave it out as in the console.
                    refresh_interval="10s"
                )
            )
        )

        index.node.add_dependency(wait_for_collection)

        ssm.StringParameter(self, "IndexNameParam",
            parameter_name="/kb/indexName",
            string_value=self.index_name
        )

        # Store OpenSearch endpoint in SSM
        ssm.StringParameter(self, "OpenSearchEndpointParam",
            parameter_name="/kb/opensearchEndpoint", 
            string_value=Fn.select(1, Fn.split("https://", self.collection.attr_collection_endpoint))

        )

        # --- CFN Outputs ---
        CfnOutput(
            self, "CollectionName",
            value=self.collection_name,
            description="Name of the OpenSearch Serverless collection for vector search"
        )
        
        CfnOutput(
            self, "CollectionArn",
            value=self.collection.attr_arn,
            description="ARN of the OpenSearch Serverless collection"
        )
        
        CfnOutput(
            self, "CollectionEndpoint",
            value=self.collection.attr_collection_endpoint,
            description="HTTPS endpoint URL of the OpenSearch Serverless collection"
        )
        
        CfnOutput(
            self, "CollectionId",
            value=self.collection.attr_id,
            description="Unique identifier of the OpenSearch Serverless collection"
        )
        
        CfnOutput(
            self, "VectorIndexName",
            value=self.index_name,
            description="Name of the vector index used for document embeddings"
        )
        
        CfnOutput(
            self, "EncryptionPolicyName",
            value=self.encryption_policy.name,
            description="Name of the OpenSearch Serverless encryption policy"
        )
        
        CfnOutput(
            self, "NetworkPolicyName",
            value=self.network_policy.name,
            description="Name of the OpenSearch Serverless network policy"
        )
        
        CfnOutput(
            self, "DataAccessPolicyName",
            value=self.data_access_policy.name,
            description="Name of the OpenSearch Serverless data access policy"
        )

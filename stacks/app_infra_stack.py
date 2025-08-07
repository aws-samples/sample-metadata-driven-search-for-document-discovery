from constructs import Construct
from aws_cdk import (
    Stack,
    aws_ec2 as ec2,
    aws_iam as iam,
    aws_ssm as ssm,
    aws_elasticloadbalancingv2 as elbv2,
    aws_elasticloadbalancingv2_targets as targets,
    CfnOutput
)

class AppInfraStack(Stack):
    def __init__(self, scope: Construct, construct_id: str, **kwargs):
        super().__init__(scope, construct_id, **kwargs)

        # Create VPC
        self.vpc = ec2.Vpc(self, "AnycompanyDemoVPC",
            vpc_name="Anycompany-demo-VPC",
            max_azs=2,
            subnet_configuration=[
                ec2.SubnetConfiguration(
                    name="PublicSubnet",
                    subnet_type=ec2.SubnetType.PUBLIC,
                    cidr_mask=24
                ),
                ec2.SubnetConfiguration(
                    name="PrivateSubnet", 
                    subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS,
                    cidr_mask=24
                )
            ],
            nat_gateways=2
        )

        #Gets the EC2 role from SSM
        self.ec2_role = iam.Role.from_role_arn(self, "EC2Role",
            role_arn=ssm.StringParameter.value_for_string_parameter(
                self, "/app/ec2RoleArn"
            )
        )
        
        # Create security group for EC2
        self.ec2_sg = ec2.SecurityGroup(self, "AnycompanyPocSG",
            vpc=self.vpc,
            security_group_name="anycompany-poc-sg",
            description="Security group for EC2 instance",
            allow_all_outbound=True
        )

        # Create security group for ALB
        self.alb_sg = ec2.SecurityGroup(self, "ALBSecurityGroup",
            vpc=self.vpc,
            description="Security group for Application Load Balancer",
            allow_all_outbound=True
        )

        # Allow HTTP traffic to ALB (restrict to your IP range)
        self.alb_sg.add_ingress_rule(
            peer=ec2.Peer.any_ipv4(),  # Change to your IP range
            connection=ec2.Port.tcp(80),
            description="HTTP access"
        )

        # Allow ALB to communicate with EC2 on port 8501
        self.ec2_sg.add_ingress_rule(
            peer=ec2.Peer.security_group_id(self.alb_sg.security_group_id),
            connection=ec2.Port.tcp(8501),
            description="Streamlit app port"
        )

        with open("streamlit-app/anycompany_search.py", "r") as f:
            app_code = f.read()

        # User data script to install and run the application
        user_data_script = ec2.UserData.for_linux()
        user_data_script.add_commands(
            "#!/bin/bash",
            "yum update -y",
            "yum install python3 python3-pip -y",
            
            # Switch to ec2-user and create application directory
            "sudo -u ec2-user bash << 'EOF'",
            "cd /home/ec2-user",
            "mkdir -p legal-tech",
            "cd legal-tech",
            
            # Create requirements.txt
            "cat > requirements.txt << 'REQUIREMENTS'",
            "streamlit",
            "boto3",
            "opensearch-py",
            "requests",
            "REQUIREMENTS",
            
            # Create the application file from your actual code
            f"cat > anycompany_search.py << 'APPCODE'",
            app_code,
            "APPCODE",
            
            # Install dependencies and start application
            "pip3 install -r requirements.txt --user",
            "nohup /home/ec2-user/.local/bin/streamlit run anycompany_search.py --server.port 8501 --server.address 0.0.0.0 > streamlit.log 2>&1 &",
            "EOF"
        )

        # Create EC2 instance
        self.instance = ec2.Instance(self, "AnycompanyDemoInstance",
            instance_type=ec2.InstanceType.of(ec2.InstanceClass.M7I, ec2.InstanceSize.LARGE),
            machine_image=ec2.MachineImage.latest_amazon_linux2023(),
            vpc=self.vpc,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PRIVATE_WITH_EGRESS),
            security_group=self.ec2_sg,
            role=self.ec2_role,
            user_data=user_data_script
        )

        # Create Application Load Balancer
        self.alb = elbv2.ApplicationLoadBalancer(self, "AnycompanyALB",
            vpc=self.vpc,
            internet_facing=True,
            security_group=self.alb_sg,
            vpc_subnets=ec2.SubnetSelection(subnet_type=ec2.SubnetType.PUBLIC)
        )

        # Create target group
        self.target_group = elbv2.ApplicationTargetGroup(self, "AnycompanyTargetGroup",
            port=8501,
            protocol=elbv2.ApplicationProtocol.HTTP,
            vpc=self.vpc,
            target_type=elbv2.TargetType.INSTANCE,
            targets=[targets.InstanceTarget(self.instance)]
        )

        # Create listener
        self.alb.add_listener("ALBListener",
            port=80,
            default_target_groups=[self.target_group]
        )

        # --- CFN Outputs ---     
        CfnOutput(
            self, "ApplicationURL",
            value=f"http://{self.alb.load_balancer_dns_name}",
            description="Complete URL to access the Streamlit search application"
        )
        
        CfnOutput(
            self, "LoadBalancerDNS",
            value=self.alb.load_balancer_dns_name,
            description="DNS name of the Application Load Balancer"
        )
        
        CfnOutput(
            self, "LoadBalancerArn",
            value=self.alb.load_balancer_arn,
            description="ARN of the Application Load Balancer"
        )
        
        CfnOutput(
            self, "InstanceId",
            value=self.instance.instance_id,
            description="ID of the EC2 instance running the Streamlit application"
        )
        
        CfnOutput(
            self, "InstancePrivateIP",
            value=self.instance.instance_private_ip,
            description="Private IP address of the EC2 instance"
        )
        
        CfnOutput(
            self, "VPCId",
            value=self.vpc.vpc_id,
            description="ID of the VPC hosting the application infrastructure"
        )
        
        CfnOutput(
            self, "TargetGroupArn",
            value=self.target_group.target_group_arn,
            description="ARN of the Application Load Balancer target group"
        )
        
        CfnOutput(
            self, "EC2SecurityGroupId",
            value=self.ec2_sg.security_group_id,
            description="ID of the security group attached to the EC2 instance"
        )
        
        CfnOutput(
            self, "ALBSecurityGroupId",
            value=self.alb_sg.security_group_id,
            description="ID of the security group attached to the Application Load Balancer"
        )
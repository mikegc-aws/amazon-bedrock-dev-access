import boto3
from botocore.exceptions import ClientError
import json

class IAMRoleManager:
    def __init__(self):
        self.iam = boto3.client('iam')
        self.sts = boto3.client('sts')

    def create_bedrock_access_role(self, role_name, user_arn, arns):
        trust_policy = {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Principal": {
                        "AWS": user_arn
                    },
                    "Action": "sts:AssumeRole"
                }
            ]
        }

        try:
            response = self.iam.create_role(
                RoleName=role_name,
                AssumeRolePolicyDocument=json.dumps(trust_policy)
            )
            
            role_arn = response['Role']['Arn']
            
            policy_document = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Action": "bedrock:InvokeModel",
                        "Resource": arns
                    }
                ]
            }
            
            self.iam.put_role_policy(
                RoleName=role_name,
                PolicyName=f"{role_name}_policy",
                PolicyDocument=json.dumps(policy_document)
            )
            
            print(f"Role '{role_name}' created successfully with ARN: {role_arn}")
            return role_arn
        
        except ClientError as e:
            print(f"Error creating role: {e}")
            return None

    def generate_temp_credentials(self, role_arn, session_name="TempSession", duration_seconds=3600):
        try:
            response = self.sts.assume_role(
                RoleArn=role_arn,
                RoleSessionName=session_name,
                DurationSeconds=duration_seconds
            )
            
            credentials = response['Credentials']
            return {
                'AccessKeyId': credentials['AccessKeyId'],
                'SecretAccessKey': credentials['SecretAccessKey'],
                'SessionToken': credentials['SessionToken'],
                'Expiration': credentials['Expiration']
            }
        
        except ClientError as e:
            print(f"Error generating temporary credentials: {e}")
            return None

    def get_role(self, role_name):
        try:
            return self.iam.get_role(RoleName=role_name)
        except self.iam.exceptions.NoSuchEntityException:
            return None

    def remove_role_policy(self, role_name):
        try:
            for policy in self.iam.list_attached_role_policies(RoleName=role_name)['AttachedPolicies']:
                self.iam.detach_role_policy(RoleName=role_name, PolicyArn=policy['PolicyArn'])
            
            for policy in self.iam.list_role_policies(RoleName=role_name)['PolicyNames']:
                self.iam.delete_role_policy(RoleName=role_name, PolicyName=policy)
        except Exception as e:
            print(f"Error removing policies from role: {e}")

    def _create_policy_document(self, selected_models):
        return {
            "Version": "2012-10-17",
            "Statement": [
                {
                    "Effect": "Allow",
                    "Action": "bedrock:InvokeModel",
                    "Resource": selected_models
                }
            ]
        }

    def update_bedrock_access_role(self, role_name, user_arn, selected_models):
        try:
            # Update trust relationship
            trust_policy = {
                "Version": "2012-10-17",
                "Statement": [
                    {
                        "Effect": "Allow",
                        "Principal": {"AWS": user_arn},
                        "Action": "sts:AssumeRole"
                    }
                ]
            }
            self.iam.update_assume_role_policy(RoleName=role_name, PolicyDocument=json.dumps(trust_policy))

            # Create and attach new policy
            policy_document = self._create_policy_document(selected_models)
            policy_name = f"{role_name}Policy"
            self.iam.put_role_policy(RoleName=role_name, PolicyName=policy_name, PolicyDocument=json.dumps(policy_document))

            return self.iam.get_role(RoleName=role_name)['Role']['Arn']
        except Exception as e:
            print(f"Error updating role: {e}")
            return None

import boto3
import sys
from tree_menu import TreeMenu
from iam_role_manager import IAMRoleManager

class Regions:
    @staticmethod
    def list():
        ec2 = boto3.client('ec2')
        response = ec2.describe_regions()
        return [
            {
                'label': region['RegionName'],
                'value': region['RegionName']
            }
            for region in response['Regions']
        ]

class Bedrock:
    def __init__(self, region="us-east-1"):
        self.bedrock = boto3.client(service_name="bedrock", region_name=region,)

    def foundation_models(self):
        response = self.bedrock.list_foundation_models(
            byInferenceType='ON_DEMAND'
        )
        model_list = []
        for model in response.get('modelSummaries', []):
            model_list.append({
                'label': model.get('modelName', ''),
                'value': model.get('modelArn', ''),
                'groupName': model.get('providerName', '')  # Changed 'provider' to 'providerName'
            })
        return model_list
    
def main():
    # Select region
    regions = Regions.list()
    region_menu = TreeMenu(regions, include_all=False, title="AWS Regions", question="Select a region:")
    selected_region = region_menu.run()
    
    if not selected_region:
        print("No region selected. Exiting.")
        return

    # Initialize Bedrock with the selected region
    bedrock = Bedrock(region=selected_region[0])
    
    # Select Bedrock models
    model_menu = TreeMenu(
        bedrock.foundation_models(),
        include_all=True,
        title=f"Region: {selected_region[0]}",
        question="Select one or more foundation models:"
    )
    selected_models = model_menu.run()
    
    print(f"\nSelected region: {selected_region[0]}")
    print(f"Selected models: {selected_models}")

    # Get the current user's ARN and extract the username
    sts_client = boto3.client('sts', region_name=selected_region[0])
    user_arn = sts_client.get_caller_identity()["Arn"]
    username = user_arn.split('/')[-1]  # Extract username from ARN

    # Create a custom role name including the username
    role_name = f"BedrockDeveloperAccess-{username}-Role"

    # Check if the role already exists
    iam_manager = IAMRoleManager()
    existing_role = iam_manager.get_role(role_name)
    if existing_role:
        overwrite = input(f"The role '{role_name}' already exists. Do you want to overwrite it? (y/n): ").lower().strip()
        if overwrite != 'y':
            print("Operation cancelled. Exiting.")
            return
        
        # Remove existing policy and update the role
        iam_manager.remove_role_policy(role_name)
        role_arn = iam_manager.update_bedrock_access_role(role_name, user_arn, selected_models)
    else:
        # Create new role
        role_arn = iam_manager.create_bedrock_access_role(role_name, user_arn, selected_models)

    if role_arn:
        print(f"\nIAM role updated/created: {role_arn}")
    else:
        print("\nFailed to update/create IAM role. Exiting.")
        return

    # Generate temporary credentials
    temp_credentials = iam_manager.generate_temp_credentials(role_arn, session_name="BedrockSession")

    if temp_credentials:
        print("\nTemporary Access Keys:")
        print(f"Access Key ID: {temp_credentials['AccessKeyId']}")
        print(f"Secret Access Key: {temp_credentials['SecretAccessKey']}")
        print(f"Session Token: {temp_credentials['SessionToken']}")
        print(f"Expiration: {temp_credentials['Expiration']}\n")
        
        # Add commands for setting environment variables
        print("\nCommands to set environment variables:")
        print("\nFor Windows (Command Prompt):")
        print(f"set AWS_ACCESS_KEY_ID={temp_credentials['AccessKeyId']}")
        print(f"set AWS_SECRET_ACCESS_KEY={temp_credentials['SecretAccessKey']}")
        print(f"set AWS_SESSION_TOKEN={temp_credentials['SessionToken']}\n") 
        
        print("\nFor macOS/Linux (Bash):")
        print(f"export AWS_ACCESS_KEY_ID={temp_credentials['AccessKeyId']}")
        print(f"export AWS_SECRET_ACCESS_KEY={temp_credentials['SecretAccessKey']}")
        print(f"export AWS_SESSION_TOKEN={temp_credentials['SessionToken']}\n")
    else:
        print("\nFailed to generate temporary credentials.")

if __name__ == "__main__":
    main()

import boto3
import sys
from tree_menu import TreeMenu
from iam_role_manager import IAMRoleManager
import time

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
    region_menu = TreeMenu(regions, include_all=False, title="AWS Regions", question="Select a region:", single_select=True)
    selected_region = region_menu.run()
    
    if not selected_region:
        print("No region selected. Exiting.")
        return

    # Initialize Bedrock with the selected region
    bedrock = Bedrock(region=selected_region[0])

    #########################################################

    # Get the current user's ARN and extract the username
    sts_client = boto3.client('sts', region_name=selected_region[0])
    user_arn = sts_client.get_caller_identity()["Arn"]
    username = user_arn.split('/')[-1]  # Extract username from ARN
    
    identity_type = ""

    # Check if the user is logged in as an IAM user or through a role assumption
    if ':user/' in user_arn:
        identity_type = "user"
    elif ':assumed-role/' in user_arn:
        identity_type = "role"
    else:
        # Handle other cases (e.g., federated user, root account)
        print(f"Logged in with an unexpected identity type: {user_arn}")

    #########################################################

    # Add duration selection menu

    if identity_type == "user":
        duration_options = [
            {'label': '15 minutes', 'value': 900},
            {'label': '1 hour', 'value': 3600},
            {'label': '4 hours', 'value': 14400},
            {'label': '12 hours (maximum)', 'value': 43200}
        ]
    else: 
        duration_options = [
            {'label': '15 minutes', 'value': 900},
            {'label': '1 hour (limit due to role chaining restriction)', 'value': 3600},
        ]
    duration_menu = TreeMenu(duration_options, include_all=False, title="Session Duration", question="Select the duration for the temporary credentials:", single_select=True)
    selected_duration = duration_menu.run()

    if not selected_duration:
        print("No duration selected. Exiting.")
        return

    duration_seconds = selected_duration[0]
    
    #########################################################


    # Select Bedrock models
    model_menu = TreeMenu(
        bedrock.foundation_models(),
        include_all=True,
        title=f"Region: {selected_region[0]}",
        question="Select one or more foundation models:"
    )
    selected_models = model_menu.run()
    
    print(f"\nSelected region: {selected_region[0]}")
    print(f"Selected model ARNs:\n-",  '\n- '.join(selected_models))

    #########################################################

    # Create a custom role name including the username
    role_name = f"BedrockDeveloperAccess-{username}-Role"

    # Check if the role already exists
    iam_manager = IAMRoleManager()
    existing_role = iam_manager.get_role(role_name)
    if existing_role:
        overwrite = input(f"\nThe role '{role_name}' already exists. Do you want to overwrite it? (y/n): ").lower().strip()
        if overwrite != 'y':
            print("Operation cancelled. Exiting.")
            return
        # Remove existing policy
        iam_manager.remove_role_policy(role_name)
        # Update or create the role and attach the policy
        role_arn = iam_manager.update_bedrock_access_role(role_name, user_arn, selected_models, duration_seconds)
    else:
        # Create new role
        role_arn = iam_manager.create_bedrock_access_role(role_name, user_arn, selected_models, duration_seconds)

    if role_arn:
        print(f"\nIAM role updated/created: {role_arn}")
    else:
        print("\nFailed to update/create IAM role. Exiting.")
        return

    # Generate temporary credentials with retry mechanism
    max_retries = 10
    base_delay = 1  # Start with a 1-second delay
    temp_credentials = None

    # Generate temporary credentials with retry mechanism, retry is needed because of eventual consistency
    for attempt in range(max_retries):
        try:
            temp_credentials = iam_manager.generate_temp_credentials(role_arn, session_name="BedrockSession", duration_seconds=duration_seconds)
            if temp_credentials:
                break
        except Exception as e:
            wait_time = base_delay * (2 ** attempt)
            print(".", end="", flush=True)
            time.sleep(wait_time)
    else:
        print("\nFailed to generate temporary credentials after multiple attempts.")

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
        print("\nFailed to generate temporary credentials after multiple attempts.")

if __name__ == "__main__":
    main()

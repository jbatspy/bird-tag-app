import boto3
import json

def lambda_handler(event, context):
    """
    Simple Lambda function to subscribe users to bird species notifications
    """
    sns = boto3.client('sns')
    
    try:
        # Parse request body
        body = json.loads(event['body']) if isinstance(event['body'], str) else event['body']
        email = body.get('email')
        species = body.get('species', '').lower().strip()
        
        # Validate inputs
        if not email or not species:
            return {
                'statusCode': 400,
                'headers': {
                    'Access-Control-Allow-Origin': '*',
                    'Content-Type': 'application/json'
                },
                'body': json.dumps({
                    'success': False,
                    'error': 'Email and species are required'
                })
            }
        
        # Get AWS account ID for topic ARN
        account_id = boto3.client('sts').get_caller_identity()['Account']
        region = 'us-east-1'
        
        # Create topic name (normalize species name)
        topic_name = f"bird-{species}-notifications"
        topic_arn = f"arn:aws:sns:{region}:{account_id}:{topic_name}"
        
        # Create topic if it doesn't exist
        try:
            sns.create_topic(Name=topic_name)
            print(f"✅ Topic created/verified: {topic_name}")
        except Exception as topic_error:
            print(f"⚠️ Topic creation warning: {topic_error}")
        
        # Subscribe user to the topic
        response = sns.subscribe(
            TopicArn=topic_arn,
            Protocol='email',
            Endpoint=email
        )
        
        subscription_arn = response.get('SubscriptionArn')
        
        print(f"✅ Subscribed {email} to {species} notifications")
        print(f"Subscription ARN: {subscription_arn}")
        
        return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'success': True,
                'message': f'Successfully subscribed to {species} notifications',
                'species': species,
                'email': email,
                'subscription_arn': subscription_arn,
                'topic_arn': topic_arn
            })
        }
        
    except Exception as e:
        print(f"❌ Error in subscription: {str(e)}")
        
        return {
            'statusCode': 500,
            'headers': {
                'Access-Control-Allow-Origin': '*',
                'Content-Type': 'application/json'
            },
            'body': json.dumps({
                'success': False,
                'error': f'Subscription failed: {str(e)}'
            })
        }
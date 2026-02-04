# create_sns_topics.py
import boto3

sns = boto3.client('sns')

# List of bird species your YOLO model can detect
bird_species = ['crow', 'kingfisher', 'myna', 'owl', 'peacock', 'pigeon', 'sparrow']

# Create SNS topic for each species
for species in bird_species:
    topic_name = f"bird-{species.lower()}-notifications"
    
    try:
        response = sns.create_topic(Name=topic_name)
        topic_arn = response['TopicArn']
        print(f"Created topic: {topic_name} with ARN: {topic_arn}")
        
        sns.set_topic_attributes(
            TopicArn=topic_arn,
            AttributeName='DisplayName',
            AttributeValue=f"{species.title()} Bird Detections"
        )
        
    except Exception as e:
        print(f"Error creating topic for {species}: {e}")
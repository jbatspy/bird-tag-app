import boto3
import os
import json
from urllib.parse import unquote_plus
from PIL import Image

s3 = boto3.client('s3')
eventbridge = boto3.client('events')

def generate_thumbnail(image_path, thumbnail_path, width=256):
    with Image.open(image_path) as img:
        aspect_ratio = img.height / img.width
        new_height = int(width * aspect_ratio)
        thumbnail = img.resize((width, new_height), Image.LANCZOS)
        thumbnail.save(thumbnail_path, format='JPEG', quality=85)

def lambda_handler(event, context):
    bucket = event['Records'][0]['s3']['bucket']['name']
    key = unquote_plus(event['Records'][0]['s3']['object']['key'])

    if not key.lower().endswith(('.jpg', '.jpeg', '.png')):
        return { 'statusCode': 200, 'body': 'Not an image, skipping.' }

    filename = key.split('/')[-1]
    tmp_image_path = f"/tmp/{filename}"
    tmp_thumb_path = "/tmp/thumb.jpg"
    thumb_key = f"thumbnails/{filename}"

    try:
        # Download original image
        s3.download_file(bucket, key, tmp_image_path)

        # Create thumbnail and upload
        generate_thumbnail(tmp_image_path, tmp_thumb_path)
        s3.upload_file(tmp_thumb_path, bucket, thumb_key)

        # Send EventBridge event to notify tagging Lambda
        eventbridge.put_events(
            Entries=[{
                'Source': 'custom.thumbnail',
                'DetailType': 'ThumbnailCreated',
                'Detail': json.dumps({
                    'bucket': bucket,
                    'key': key,
                    'thumbnail_key': thumb_key
                }),
                'EventBusName': 'default'
            }]
        )

        return { 'statusCode': 200, 'body': f"Thumbnail created and event sent for {key}" }

    except Exception as e:
        return { 'statusCode': 500, 'body': str(e) }

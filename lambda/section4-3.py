import json
import os
import boto3
from boto3.dynamodb.conditions import Key, Attr
from urllib.parse import urlparse
from decimal import Decimal

# Custom JSON encoder to handle Decimal types
class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o % 1 == 0 else float(o)
        return super(DecimalEncoder, self).default(o)

# Initialize AWS services
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('BirdDetectionsResults')
s3 = boto3.client('s3')

def lambda_handler(event, context):
    http_method = event['httpMethod']
    path = event['path']
    
    # Route based on path and method
    if path == '/search-by-tag' and http_method == 'GET':
        return handle_tag_search(event)
        
    elif path == '/search-by-species' and http_method == 'GET':
        return handle_species_search(event)
            
    elif path == '/search-by-thumbnail' and http_method == 'GET':
        return handle_thumbnail_search(event)
        
    elif path == '/tags' and http_method == 'POST':
        return handle_bulk_tags(event)
        
    elif path == '/delete' and http_method == 'DELETE':
        return handle_file_deletion(event)
        
    else:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Invalid request'}),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }


def handle_tag_search(event):
    params = event.get('queryStringParameters', {}) or {}
    tag_requirements = {}
    i = 1
    while f'tag{i}' in params:
        tag = params[f'tag{i}']
        count = int(params.get(f'count{i}', 1))
        # Capitalize to match your data format
        tag_capitalized = tag.capitalize()
        tag_requirements[tag_capitalized] = count
        i += 1

    if not tag_requirements:
        return {
            'statusCode': 200, 
            'body': json.dumps({'links': []}),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }
    
    try:
        response = table.scan()
        all_items = response.get('Items', [])
        matching_items = []
        
        for item in all_items:
            matches_all_requirements = True
            
            # Check if detections object exists
            detections = item.get('detections', {})
            
            # Check each tag requirement
            for required_tag, required_count in tag_requirements.items():
                if required_tag not in detections:
                    matches_all_requirements = False
                    break
                
                # Get the actual count
                actual_count = detections[required_tag]
                if isinstance(actual_count, Decimal):
                    actual_count = int(actual_count)
                
                if actual_count < required_count:
                    matches_all_requirements = False
                    break
            
            if matches_all_requirements:
                matching_items.append(item)
        
        links = process_results(matching_items)
        
        return {
            'statusCode': 200, 
            'body': json.dumps({'links': links}, cls=DecimalEncoder),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }
        
    except Exception as e:
        print(f"Error in handle_tag_search: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Internal server error: {str(e)}'}),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }


def handle_species_search(event):
    params = event.get('queryStringParameters', {})
    species = params.get('species', '').capitalize()

    try:
        response = table.scan()
        matching_items = []
        
        for item in response.get('Items', []):
            detections = item.get('detections', {})
            if species in detections:
                matching_items.append(item)

        result = process_results(matching_items)

        return {
            'statusCode': 200,
            'body': json.dumps({'links': result}, cls=DecimalEncoder),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)}),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }


def handle_thumbnail_search(event):
    """
    Find files based on the thumbnail's URL.
    """
    params = event.get('queryStringParameters', {})
    thumbnail_url = params.get('thumbnail_url', '')
    
    if not thumbnail_url:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'thumbnail_url parameter is required'}),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }
    
    try:
        # Extract the file ID from thumbnail URL
        # Your thumbnailURL format: s3://g146-a3/thumbnails/pigeon_2.jpg
        # Your fileID format: images/pigeon_2.jpg
        
        if 's3://g146-a3/thumbnails/' in thumbnail_url:
            thumbnail_file = thumbnail_url.replace('s3://g146-a3/thumbnails/', '')
            # The fileID has images/ prefix, but thumbnail doesn't
            file_id = f"images/{thumbnail_file}"
        else:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'Invalid thumbnail URL format'}),
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                }
            }
        
        # Query DynamoDB for the original file
        response = table.scan()
        matching_items = []
        
        for item in response.get('Items', []):
            if item.get('fileID') == file_id:
                matching_items.append(item)
        
        if not matching_items:
            return {
                'statusCode': 404,
                'body': json.dumps({'error': 'Original file not found'}),
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                }
            }
        
        # Return the full-size image URL
        original_item = matching_items[0]
        full_size_url = original_item.get('originalURL', '')
        
        return {
            'statusCode': 200,
            'body': json.dumps({'full_size_url': full_size_url}, cls=DecimalEncoder),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }
        
    except Exception as e:
        return {
            'statusCode': 500,
            'body': json.dumps({'error': str(e)}),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }


def handle_bulk_tags(event):
    """
    Manual addition or removal of tags with bulk tagging.
    """
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Invalid JSON body'}),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }
    
    urls = body.get('url', [])
    operation = body.get('operation', 1)  # 1 for add, 0 for remove
    tags = body.get('tags', [])
    
    if not urls or not tags:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Missing required fields: url and tags'}),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }
    
    # Parse tags into dict {species: count}
    tag_dict = {}
    for tag in tags:
        parts = tag.split(',')
        if len(parts) == 2:
            species = parts[0].strip().capitalize()
            count = int(parts[1].strip())
            tag_dict[species] = count
    
    # Process each URL
    updated_files = []
    for url in urls:
        # Extract file ID from URL
        if 's3://g146-a3/thumbnails/' in url:
            thumbnail_file = url.replace('s3://g146-a3/thumbnails/', '')
            file_id = f"images/{thumbnail_file}"
        elif 's3://g146-a3/' in url:
            file_id = url.replace('s3://g146-a3/', '')
        else:
            continue
        
        # Get current item from DynamoDB
        response = table.scan()
        matching_items = []
        for item in response.get('Items', []):
            if item.get('fileID') == file_id:
                matching_items.append(item)
        
        if matching_items:
            item = matching_items[0]
            detections = item.get('detections', {})
            
            # Add or remove tags based on operation
            for species, count in tag_dict.items():
                if operation == 1:  # Add tags
                    current_count = detections.get(species, 0)
                    detections[species] = current_count + count
                else:  # Remove tags
                    if species in detections:
                        current_count = detections[species]
                        new_count = current_count - count
                        if new_count <= 0:
                            del detections[species]
                        else:
                            detections[species] = new_count
            
            # Update item in DynamoDB
            item['detections'] = detections
            table.put_item(Item=item)
            updated_files.append(file_id)
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': f'Successfully updated {len(updated_files)} files',
            'updated_files': updated_files
        }, cls=DecimalEncoder),
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        }
    }


def handle_file_deletion(event):
    """
    Delete files and their thumbnails from S3 and remove entries from DynamoDB.
    """
    try:
        body = json.loads(event.get('body', '{}'))
    except json.JSONDecodeError:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Invalid JSON body'}),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }
    
    urls = body.get('urls', [])
    
    if not urls:
        return {
            'statusCode': 400,
            'body': json.dumps({'error': 'Missing required field: urls'}),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }
    
    deleted_files = []
    
    for url in urls:
        # Extract file ID from URL
        if 's3://g146-a3/' in url:
            file_id = url.replace('s3://g146-a3/', '')
        else:
            continue
        
        # Delete main file from S3
        s3.delete_object(Bucket='g146-a3', Key=file_id)
        
        # For images, also delete thumbnail
        file_extension = file_id.split('.')[-1].lower() if '.' in file_id else ''
        if file_extension in ['jpg', 'jpeg', 'png']:
            # Delete thumbnail from S3
            thumbnail_key = f"thumbnails/{file_id.split('/')[-1]}"
            s3.delete_object(Bucket='g146-a3', Key=thumbnail_key)
        
        # Delete record from DynamoDB
        table.delete_item(Key={'fileID': file_id})
        deleted_files.append(file_id)
    
    return {
        'statusCode': 200,
        'body': json.dumps({
            'message': f'Successfully deleted {len(deleted_files)} files',
            'deleted_files': deleted_files
        }, cls=DecimalEncoder),
        'headers': {
            'Content-Type': 'application/json',
            'Access-Control-Allow-Origin': '*'
        }
    }


def process_results(items):
    """
    Process DynamoDB items and return appropriate URLs based on file type.
    For images: return thumbnail URLs
    For videos/audio: return full file URLs
    """
    links = []
    
    for item in items:
        file_id = item.get('fileID', '')
        file_type = item.get('fileType', '').upper()
        
        if file_type in ['JPG', 'JPEG', 'PNG', 'IMAGE']:
            # For images, return thumbnail URL
            thumbnail_url = item.get('thumbnailURL', '')
            if thumbnail_url:
                # Convert s3:// URL to https:// URL
                if thumbnail_url.startswith('s3://g146-a3/'):
                    https_url = thumbnail_url.replace('s3://g146-a3/', 'https://g146-a3.s3.amazonaws.com/')
                    links.append(https_url)
                else:
                    links.append(thumbnail_url)
            
        elif file_type in ['MP4', 'AVI', 'MOV', 'WAV', 'MP3', 'FLAC', 'VIDEO', 'AUDIO']:
            # For videos and audio, return original URL
            original_url = item.get('originalURL', '')
            if original_url:
                # Convert s3:// URL to https:// URL
                if original_url.startswith('s3://g146-a3/'):
                    https_url = original_url.replace('s3://g146-a3/', 'https://g146-a3.s3.amazonaws.com/')
                    links.append(https_url)
                else:
                    links.append(original_url)
    
    return links
# lambda_file_search.py
import json
import boto3
import base64
import os
import shutil
import cv2
import numpy as np
from decimal import Decimal

# Model setup (EXACTLY same as your tagging function)
MODEL_SRC_PATH = '/var/task/model.pt'
MODEL_DST_PATH = '/tmp/model.pt'

if not os.path.exists(MODEL_DST_PATH):
    shutil.copyfile(MODEL_SRC_PATH, MODEL_DST_PATH)

# Set torch to use weights_only=False for YOLO models
import torch
original_load = torch.load
def patched_load(*args, **kwargs):
    if 'weights_only' not in kwargs:
        kwargs['weights_only'] = False
    return original_load(*args, **kwargs)
torch.load = patched_load

from ultralytics import YOLO
model = YOLO(MODEL_DST_PATH)

# Initialize AWS clients
dynamodb = boto3.resource('dynamodb')
table = dynamodb.Table('BirdDetectionsResults')

class DecimalEncoder(json.JSONEncoder):
    def default(self, o):
        if isinstance(o, Decimal):
            return int(o) if o % 1 == 0 else float(o)
        return super(DecimalEncoder, self).default(o)

def detect_birds_in_file(file_content, file_extension):
    """
    Detect birds in the uploaded file content.
    Returns a set of bird species found.
    """
    if file_extension.lower() in ['jpg', 'jpeg', 'png']:
        return detect_birds_in_image(file_content)
    elif file_extension.lower() in ['mp4', 'avi', 'mov']:
        return detect_birds_in_video(file_content)
    else:
        raise ValueError(f"Unsupported file type: {file_extension}")

def detect_birds_in_image(image_bytes):
    """Process image bytes and return detected bird species."""
    np_arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    
    results = model(img)[0]
    detected_species = set()
    
    for box in results.boxes:
        if box.conf > 0.5:  # Confidence threshold
            class_id = int(box.cls)
            class_name = model.names[class_id]
            detected_species.add(class_name)
    
    return detected_species

def detect_birds_in_video(video_bytes):
    """Process video bytes and return detected bird species."""
    # Save video to temp file
    temp_video_path = '/tmp/query_video.mp4'
    with open(temp_video_path, 'wb') as f:
        f.write(video_bytes)
    
    detected_species = set()
    cap = cv2.VideoCapture(temp_video_path)
    
    if not cap.isOpened():
        raise Exception("Unable to open video file")
    
    try:
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        if frame_count == 0:
            return detected_species
        
        # Sample 10 frames evenly distributed
        sample_indices = np.linspace(0, frame_count - 1, num=10, dtype=int)
        
        for idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret:
                continue
            
            results = model(frame)[0]
            for box in results.boxes:
                if box.conf > 0.5:  # Confidence threshold
                    class_id = int(box.cls)
                    class_name = model.names[class_id]
                    detected_species.add(class_name)
    
    finally:
        cap.release()
        # Clean up temp file
        if os.path.exists(temp_video_path):
            os.remove(temp_video_path)
    
    return detected_species

def find_matching_files(detected_species):
    """
    Find all files in DynamoDB that contain ALL the detected species.
    """
    if not detected_species:
        return []
    
    # Scan all items in DynamoDB
    response = table.scan()
    all_items = response.get('Items', [])
    matching_items = []
    
    for item in all_items:
        detections = item.get('detections', {})
        item_species = set(detections.keys())
        
        # Check if all detected species are present in this item
        if detected_species.issubset(item_species):
            matching_items.append(item)
    
    return matching_items

def process_results(items):
    """
    Process DynamoDB items and return appropriate URLs based on file type.
    """
    links = []
    
    for item in items:
        file_type = item.get('fileType', '').lower()
        
        if file_type in ['jpg', 'jpeg', 'png', 'image']:
            # For images, return thumbnail URL
            thumbnail_url = item.get('thumbnailURL', '')
            if thumbnail_url and thumbnail_url.startswith('s3://g146-a3/'):
                https_url = thumbnail_url.replace('s3://g146-a3/', 'https://g146-a3.s3.amazonaws.com/')
                links.append(https_url)
        
        elif file_type in ['mp4', 'avi', 'mov', 'video', 'wav', 'mp3', 'flac']:
            # For videos and audio, return original URL
            original_url = item.get('originalURL', '')
            if original_url and original_url.startswith('s3://g146-a3/'):
                https_url = original_url.replace('s3://g146-a3/', 'https://g146-a3.s3.amazonaws.com/')
                links.append(https_url)
    
    return links

def lambda_handler(event, context):
    """
    Lambda handler for file-based search.
    Expects a POST request with file content in the body.
    """
    try:
        # Check if it's a POST request
        if event.get('httpMethod') != 'POST':
            return {
                'statusCode': 405,
                'body': json.dumps({'error': 'Method not allowed. Use POST.'}),
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                }
            }
        
        # Parse the request body
        body = event.get('body', '')
        if event.get('isBase64Encoded', False):
            body = base64.b64decode(body)
        
        # Extract file content and metadata
        # Assuming multipart/form-data or direct file upload
        # You might need to adjust this based on your frontend implementation
        
        # For now, assuming the body contains the raw file data
        # and filename is passed as a query parameter
        params = event.get('queryStringParameters', {}) or {}
        filename = params.get('filename', 'uploaded_file')
        file_extension = filename.split('.')[-1] if '.' in filename else ''
        
        if not file_extension:
            return {
                'statusCode': 400,
                'body': json.dumps({'error': 'File extension not provided'}),
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                }
            }
        
        # Convert body to bytes if it's a string
        if isinstance(body, str):
            file_content = body.encode()
        else:
            file_content = body
        
        # Detect birds in the uploaded file
        detected_species = detect_birds_in_file(file_content, file_extension)
        
        if not detected_species:
            return {
                'statusCode': 200,
                'body': json.dumps({
                    'detected_species': [],
                    'matching_files': [],
                    'message': 'No birds detected in the uploaded file'
                }),
                'headers': {
                    'Content-Type': 'application/json',
                    'Access-Control-Allow-Origin': '*'
                }
            }
        
        # Find matching files in DynamoDB
        matching_items = find_matching_files(detected_species)
        result_links = process_results(matching_items)
        
        return {
            'statusCode': 200,
            'body': json.dumps({
                'detected_species': list(detected_species),
                'matching_files': result_links,
                'total_matches': len(result_links)
            }, cls=DecimalEncoder),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }
    
    except Exception as e:
        print(f"Error in file-based search: {str(e)}")
        return {
            'statusCode': 500,
            'body': json.dumps({'error': f'Internal server error: {str(e)}'}),
            'headers': {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            }
        }
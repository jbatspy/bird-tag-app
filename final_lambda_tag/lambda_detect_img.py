import boto3
import json
import os
import shutil
from ultralytics import YOLO
import numpy as np
import cv2

# Copy YOLO model from read-only to writable layer
MODEL_SRC_PATH = '/var/task/model.pt'
MODEL_DST_PATH = '/tmp/model.pt'

if not os.path.exists(MODEL_DST_PATH):
    shutil.copyfile(MODEL_SRC_PATH, MODEL_DST_PATH)

# Load model
model = YOLO(MODEL_DST_PATH)

# AWS Clients
s3 = boto3.client('s3')
dynamodb = boto3.resource('dynamodb')

def process_image(image_bytes):
    """Detect birds in image."""
    np_arr = np.frombuffer(image_bytes, np.uint8)
    img = cv2.imdecode(np_arr, cv2.IMREAD_COLOR)
    results = model(img)[0]

    class_counts = {}
    for box in results.boxes:
        class_id = int(box.cls)
        class_name = model.names[class_id]
        class_counts[class_name] = class_counts.get(class_name, 0) + 1

    return class_counts

def process_video(video_path):
    """Detect birds in 10 sampled frames of a video."""
    max_counts = {}
    cap = cv2.VideoCapture(video_path)
    if not cap.isOpened():
        raise Exception("Unable to open video file")

    try:
        frame_count = int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
        sample_indices = np.linspace(0, frame_count - 1, num=10, dtype=int)

        for idx in sample_indices:
            cap.set(cv2.CAP_PROP_POS_FRAMES, idx)
            ret, frame = cap.read()
            if not ret:
                continue

            results = model(frame)[0]
            frame_counts = {}
            for box in results.boxes:
                class_id = int(box.cls)
                class_name = model.names[class_id]
                frame_counts[class_name] = frame_counts.get(class_name, 0) + 1

            for bird, count in frame_counts.items():
                if bird not in max_counts or count > max_counts[bird]:
                    max_counts[bird] = count
    finally:
        cap.release()

    return max_counts

def lambda_handler(event, context):
    """Triggered by EventBridge when a thumbnail is created."""
    try:
        detail = event['detail']
        bucket = detail['bucket']
        key = detail['key']
        thumbnail_key = detail.get('thumbnail_key', None)
        file_extension = key.split(".")[-1].lower()

        if file_extension in ["jpg", "jpeg", "png"]:
            file_type = "IMAGE"
            tmp_path = f"/tmp/{key.split('/')[-1]}"
            s3.download_file(bucket, key, tmp_path)

            with open(tmp_path, "rb") as f:
                file_bytes = f.read()

            detection_results = process_image(file_bytes)

        elif file_extension in ["mp4", "avi", "mov"]:
            file_type = "VIDEO"
            tmp_path = f"/tmp/{key.split('/')[-1]}"
            s3.download_file(bucket, key, tmp_path)

            detection_results = process_video(tmp_path)
            thumbnail_key = None  # No thumbnail for videos

        else:
            return {
                'statusCode': 400,
                'body': f"Unsupported file type: {file_extension}"
            }

        # Prepare DynamoDB record
        record = {
            'fileID': key,
            'fileType': file_type,
            'detections': detection_results,
            'originalURL': f"s3://{bucket}/{key}",
            'thumbnailURL': f"s3://{bucket}/{thumbnail_key}" if thumbnail_key else None
        }

        table = dynamodb.Table('BirdDetectionsResults')
        table.put_item(Item=record)

        return {
            'statusCode': 200,
            'fileType': file_type,
            'detections': detection_results
        }

    except Exception as e:
        print("Error:", str(e))
        return {
            'statusCode': 500,
            'body': str(e)
        }

# BirdTag

A serverless AWS platform for wildlife media management. Built with Flask, S3, Lambda, and DynamoDB, it uses YOLO ML models to automatically detect and tag bird species in images/videos. Features Cognito authentication, thumbnail generation, RESTful search APIs, bulk tag operations, and SNS notifications.

## Architecture

This project implements a fully serverless, event-driven architecture leveraging multiple AWS services:

- **Frontend**: Flask web application with Jinja2 templates
- **Authentication**: AWS Cognito for user management and JWT-based auth
- **Storage**: S3 buckets organized by media type (images/, videos/, audio/)
- **Compute**: AWS Lambda functions triggered by S3 events and API Gateway
- **Database**: DynamoDB for metadata storage and fast queries
- **Notifications**: SNS topics for species-based email alerts
- **ML Pipeline**: YOLO model deployed on Lambda for real-time object detection

## Technologies Used

- **Backend**: Python 3.11, Flask, boto3
- **Machine Learning**: Ultralytics YOLO, OpenCV, NumPy
- **AWS Services**: Lambda, S3, DynamoDB, API Gateway, Cognito, SNS, EventBridge
- **Authentication**: AWS Cognito User Pools with HMAC secret hash
- **Frontend**: HTML5, CSS3, JavaScript

## Problem Statement

Wildlife researchers and bird enthusiasts need a centralized, searchable repository for media files. Manual tagging is time-consuming and error-prone. This system automates species detection and enables intelligent search capabilities across large media collections.

## Key Features

### Core Functionality
- **Automated Bird Detection**: YOLO-based ML model detects and counts bird species in images and videos
- **Multi-format Support**: Handles images (JPG, PNG), videos (MP4, AVI, MOV), and audio files
- **Event-driven Processing**: S3 uploads automatically trigger Lambda functions for thumbnail generation and tagging
- **Secure Authentication**: Full user management with email verification via Cognito

### Search & Query APIs
- **Tag-based Search**: Find media by species and minimum counts (e.g., "≥3 crows AND ≥2 pigeons")
- **Species Search**: Retrieve all files containing at least one instance of a species
- **Thumbnail Search**: Look up full-size images from thumbnail URLs
- **Visual Similarity Search**: Upload a file to find similar media based on detected species
- **Bulk Operations**: Add or remove tags from multiple files simultaneously

### Advanced Features
- **Automatic Thumbnail Generation**: Lambda resizes images maintaining aspect ratio
- **Real-time Notifications**: Users subscribe to species-specific SNS topics for email alerts
- **File Management**: Delete files and thumbnails with automatic database cleanup
- **Pre-signed URLs**: Direct-to-S3 uploads for large files without server bottlenecks

## Architecture Highlights

### Event-Driven Flow
1. User uploads media → S3 bucket
2. S3 event triggers thumbnail Lambda (for images)
3. EventBridge triggers detection Lambda
4. YOLO model processes file, extracts bird species and counts
5. Results stored in DynamoDB with S3 URLs
6. SNS notifications sent to subscribed users

### Lambda Functions
- `thumbnail/`: Image resizing with Pillow
- `final_lambda_tag/lambda_detect_img.py`: YOLO-based detection for images/videos
- `lambda/search_by_file/`: Visual similarity search
- `lambda/SNS_notification/`: Subscription management
- `lambda/section4-3.py`: Query endpoints (tags, species, bulk operations)

## Project Structure

```
bird-tag-app/
├── BirdTag App/
│   ├── app.py                    # Flask application
│   ├── templates/                # HTML templates
│   └── setup.py                  # Package configuration
├── lambda/                       # Lambda function code
│   ├── search_by_file/
│   ├── SNS_notification/
│   └── section4-3.py
├── final_lambda_tag/             # ML detection Lambda
│   └── lambda_detect_img.py
└── thumbnail/                    # Dependencies for thumbnail Lambda
```

## Setup & Deployment

### Prerequisites
- AWS Account with appropriate IAM permissions
- Python 3.11+
- AWS CLI configured

### Local Development
```bash
# Clone repository
git clone <repository-url>
cd bird-tag-app

# Install dependencies
pip install flask boto3 werkzeug flask-cors requests pyjwt

# Configure AWS credentials
aws configure

# Run Flask app
cd "BirdTag App"
python app.py
```

### AWS Configuration

1. **Create S3 Bucket**: For media storage with folders: `images/`, `videos/`, `audio/`
2. **Set up DynamoDB Table**: `BirdDetectionsResults` with `fileID` as primary key
3. **Deploy Lambda Functions**: Package with dependencies and upload to AWS
4. **Configure Cognito User Pool**: Enable email verification and create app client
5. **Set up API Gateway**: Create REST APIs pointing to Lambda functions
6. **Configure S3 Event Notifications**: Trigger Lambdas on object creation
7. **Create SNS Topics**: For species-specific notifications

### Environment Variables (app.py)
```python
COGNITO_CLIENT_ID = 'your-client-id'
COGNITO_CLIENT_SECRET = 'your-client-secret'
COGNITO_USER_POOL_ID = 'your-pool-id'
COGNITO_REGION = 'us-east-1'
S3_BUCKET = 'your-bucket-name'
S3_REGION = 'us-east-1'
```

## API Endpoints

- `POST /api/upload` - Upload media file to S3
- `POST /tags-counts-search` - Search by species with counts
- `POST /species-search` - Search by species (any count)
- `GET /thumbnail-search` - Get full image from thumbnail URL
- `POST /file-search` - Find similar files based on uploaded image
- `POST /tags-update` - Bulk add/remove tags
- `POST /file-deletion` - Delete files and metadata
- `POST /api/subscribe` - Subscribe to species notifications

## Technical Achievements

- **Serverless Architecture**: Zero server management, automatic scaling
- **Event-Driven Design**: Decoupled components with EventBridge orchestration
- **ML Model Deployment**: YOLO model packaged and optimized for Lambda cold starts
- **Video Processing**: Intelligent frame sampling (10 frames) for efficient bird detection
- **Security**: JWT tokens, Cognito authentication, IAM role-based access control
- **Cost Optimization**: Pre-signed URLs reduce data transfer costs

## Future Enhancements

- Implement CloudFront CDN for faster media delivery
- Add audio bird call detection using spectral analysis
- Deploy frontend as static site on S3 + CloudFront
- Implement CI/CD pipeline with AWS CodePipeline
- Add real-time collaboration features with WebSockets (API Gateway)
- Integrate AWS Rekognition for additional metadata extraction

## License

This project is available for demonstration and educational purposes.

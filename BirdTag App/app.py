from werkzeug.utils import secure_filename
import os
import hmac
import hashlib
import base64
import boto3
import json
import jwt
import requests
from datetime import datetime
import uuid

from flask import (
    Flask, render_template, request, redirect, url_for,
    session, flash, Response, jsonify
)
from werkzeug.utils import secure_filename
from flask_cors import CORS

app = Flask(__name__)
app.secret_key = os.urandom(24)
CORS(app)

# Cognito Config
COGNITO_CLIENT_ID = os.environ.get('COGNITO_CLIENT_ID', 'your-client-id-here')
COGNITO_CLIENT_SECRET = os.environ.get('COGNITO_CLIENT_SECRET', 'your-secret-here')
COGNITO_USER_POOL_ID = os.environ.get('COGNITO_USER_POOL_ID', 'your-pool-id-here')
COGNITO_REGION = os.environ.get('COGNITO_REGION', 'us-east-1')

# S3 Config

S3_BUCKET = os.environ.get('S3_BUCKET', 'your-bucket-name')
S3_REGION = os.environ.get('S3_REGION', 'us-east-1')

# Upload Config
ALLOWED_EXTENSIONS = {'png', 'jpg', 'jpeg', 'gif', 'mp4', 'avi', 'mov', 'mp3', 'wav', 'flac'}
MAX_FILE_SIZE = 50 * 1024 * 1024  # 50MB

# Clients
cognito_client = boto3.client('cognito-idp', region_name=COGNITO_REGION)
s3_client = boto3.client('s3', region_name=S3_REGION)

# ----------------------------------------------------------------------------
# Make `user` available in every template as a dict with `username` and `email`
# ----------------------------------------------------------------------------
@app.context_processor
def inject_user():
    return dict(user=session.get("user", {}))

def get_secret_hash(username):
    msg = username + COGNITO_CLIENT_ID
    dig = hmac.new(
        bytes(COGNITO_CLIENT_SECRET, 'utf-8'),
        msg=bytes(msg, 'utf-8'),
        digestmod=hashlib.sha256
    ).digest()
    return base64.b64encode(dig).decode()


def allowed_file(filename):
    return '.' in filename and \
           filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def get_file_type(filename):
    """Determine file type based on extension"""
    ext = filename.rsplit('.', 1)[1].lower()
    if ext in ['png', 'jpg', 'jpeg', 'gif']:
        return 'image'
    elif ext in ['mp4', 'avi', 'mov']:
        return 'video'
    elif ext in ['mp3', 'wav', 'flac']:
        return 'audio'
    return 'unknown'

def require_auth(f):
    """Decorator to require authentication"""
    def decorated_function(*args, **kwargs):
        if 'access_token' not in session:
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    decorated_function.__name__ = f.__name__
    return decorated_function


@app.route('/')
def index():
    if 'access_token' in session:
        return redirect(url_for('dashboard'))
    return redirect(url_for('login'))

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        given_name = request.form['first_name']
        family_name = request.form['last_name']
        try:
            cognito_client.sign_up(
                ClientId=COGNITO_CLIENT_ID,
                Username=email,
                Password=password,
                SecretHash=get_secret_hash(email),
                UserAttributes=[
                    {'Name': 'email', 'Value': email},
                    {'Name': 'given_name', 'Value': given_name},
                    {'Name': 'family_name', 'Value': family_name}
                ]
            )
            return redirect(url_for('confirm', email=email))
        except cognito_client.exceptions.UsernameExistsException:
            return "User already exists."
        except Exception as e:
            return f"Error during sign-up: {str(e)}"
    return render_template('signup.html')

@app.route('/confirm', methods=['GET', 'POST'])
def confirm():
    if request.method == 'POST':
        email = request.form['email']
        code = request.form['code']
        try:
            cognito_client.confirm_sign_up(
                ClientId=COGNITO_CLIENT_ID,
                Username=email,
                ConfirmationCode=code,
                SecretHash=get_secret_hash(email)
            )
            return redirect(url_for('login'))
        except Exception as e:
            return f"Error confirming sign-up: {str(e)}"
    email_prefill = request.args.get('email', '')
    return render_template('confirm.html', email=email_prefill)

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        try:
            resp = cognito_client.initiate_auth(
                ClientId=COGNITO_CLIENT_ID,
                AuthFlow='USER_PASSWORD_AUTH',
                AuthParameters={
                    'USERNAME': email,
                    'PASSWORD': password,
                    'SECRET_HASH': get_secret_hash(email)
                }
            )
            session['access_token'] = resp['AuthenticationResult']['AccessToken']
            session['user'] = email
            return redirect(url_for('dashboard'))
        except cognito_client.exceptions.NotAuthorizedException:
            return "Incorrect username or password."
        except Exception as e:
            return f"Login failed: {str(e)}"
    return render_template('login.html')

@app.route('/dashboard', methods=['GET', 'POST'])
def dashboard():
    if 'access_token' not in session:
        return redirect(url_for('login'))

    return render_template('dashboard_main.html', user=session.get('user'))

@app.route('/subscribe', methods=['GET', 'POST'])
def subscribe():
    if 'access_token' not in session:
        return redirect(url_for('login'))

    return render_template('subscribe.html', user=session.get('user'))

@app.route("/upload", methods=["GET"])
def upload():
    if not session.get("user"):
        return redirect(url_for("login"))
    return render_template("upload.html")


@app.route("/search")
def search():
    """
    Serve the search UI.
    """
    if not session.get("user"):
        return redirect(url_for("login"))
    return render_template("search.html")

@app.route("/generate-presigned-url", methods=["POST"])
def generate_presigned_url():
    """
    Generates a pre-signed POST URL so the client can upload directly to S3.
    Automatically places files into 'images/', 'video/', or 'audio/' folders 
    based on the MIME type. Returns a region-specific URL.
    """
    if not session.get("user"):
        return jsonify({"error": "Not authenticated"}), 403

    data = request.get_json()
    filename = data.get("filename")
    folder = data.get("folder", "others/")
    print(folder)
    if not filename:
        return jsonify({"error": "Missing filename"}), 400

    # Determine content-type prefix from folder
    if folder.startswith("images"):
        content_type_prefix = "image/"
        default_content_type = "image/jpeg"
    elif folder.startswith("video"):
        content_type_prefix = "video/"
        default_content_type = "video/mp4"
    elif folder.startswith("audio"):
        content_type_prefix = "audio/"
        default_content_type = "audio/mpeg"
    else:
        content_type_prefix = ""
        default_content_type = "application/octet-stream"

    key = f"{folder}{filename}"

    # Build fields and conditions for the presigned POST
    fields = {
        "acl": "public-read",
        "Content-Type": default_content_type
    }
    conditions = [
        {"acl": "public-read"},
        ["starts-with", "$Content-Type", content_type_prefix]
    ]

    try:
        presigned = s3_client.generate_presigned_post(
            Bucket=S3_BUCKET,
            Key=key,
            Fields=fields,
            Conditions=conditions,
            ExpiresIn=3600
        )
        # Overwrite default S3 base URL with region-specific endpoint
        presigned["url"] = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/"
        presigned["fields"]["bucket"] = S3_BUCKET
        presigned["fields"]["region"] = S3_REGION
        presigned["fields"]["key"] = key
        return jsonify(presigned)
    except Exception as e:
        return jsonify({"error": str(e)}), 500


#--------------------------------------------------------#
#                        Queries                         #
#--------------------------------------------------------#
# Base API URL for your Lambda functions
LAMBDA_API_BASE = os.environ.get('LAMBDA_API_BASE', 'https://your-api.amazonaws.com/dev')

@app.route('/tags-counts-search', methods=['POST'])
def tags_counts_search():
    """Proxy for search-by-tag Lambda function"""
    if not session.get("user"):
        return jsonify({"error": "Not authenticated"}), 403
    
    try:
        # Get the JSON data from frontend
        data = request.get_json()
        
        # Convert to query parameters format expected by Lambda
        params = {}
        i = 1
        for tag, count in data.items():
            params[f'tag{i}'] = tag
            params[f'count{i}'] = str(count)
            i += 1
        
        # Make request to Lambda
        response = requests.get(f"{LAMBDA_API_BASE}/search-by-tag", params=params)
        
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/species-search', methods=['POST'])
def species_search():
    """Proxy for search-by-species Lambda function"""
    if not session.get("user"):
        return jsonify({"error": "Not authenticated"}), 403
    
    try:
        # Expecting {"species": "crow"} format from frontend
        data = request.get_json()
        species = list(data.keys())[0] if data else ""
        
        # Make request to Lambda
        response = requests.get(f"{LAMBDA_API_BASE}/search-by-species", params={"species": species})
        
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/thumbnail-search', methods=['GET'])
def thumbnail_search():
    """Proxy for search-by-thumbnail Lambda function"""
    if not session.get("user"):
        return jsonify({"error": "Not authenticated"}), 403
    
    try:
        thumbnail_url = request.args.get('url')
        
        # Make request to Lambda
        response = requests.get(f"{LAMBDA_API_BASE}/search-by-thumbnail", params={"thumbnail_url": thumbnail_url})
        
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/file-search', methods=['POST'])
def file_search():
    """Proxy for file-based-search Lambda function"""
    if not session.get("user"):
        return jsonify({"error": "Not authenticated"}), 403
    
    try:
        # Get uploaded file
        file = request.files.get('file')
        if not file:
            return jsonify({"error": "No file provided"}), 400
        
        # Read file content
        file_content = file.read()
        
        # Get access token from session
        access_token = session.get('access_token')
        
        # Make request to Lambda with authentication
        headers = {
            "Content-Type": "application/octet-stream",
            "Authorization": f"Bearer {access_token}"  # or just access_token depending on your setup
        }
        
        response = requests.post(
            f"{LAMBDA_API_BASE}/file_based_search", 
            params={"filename": file.filename},
            data=file_content,
            headers=headers
        )
        
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/tags-update', methods=['POST'])
def tags_update():
    """Proxy for tags Lambda function (bulk add/remove)"""
    if not session.get("user"):
        return jsonify({"error": "Not authenticated"}), 403
    
    try:
        data = request.get_json()
        
        # Make request to Lambda
        response = requests.post(f"{LAMBDA_API_BASE}/tags", json=data)
        
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500

@app.route('/file-deletion', methods=['POST'])
def file_deletion():
    """Proxy for delete Lambda function"""
    if not session.get("user"):
        return jsonify({"error": "Not authenticated"}), 403
    
    try:
        data = request.get_json()
        
        # Make request to Lambda
        response = requests.delete(f"{LAMBDA_API_BASE}/delete", json=data)
        
        return jsonify(response.json()), response.status_code
    except Exception as e:
        return jsonify({"error": str(e)}), 500



@app.route('/api/upload', methods=['POST'])
@require_auth
def upload_file():
    print(request.files)
    try:
        if 'file' not in request.files:
            return jsonify({'error': 'No file selected'}), 400
        
        file = request.files['file']
        if file.filename == '':
            return jsonify({'error': 'No file selected'}), 400
        
        if not allowed_file(file.filename):
            return jsonify({'error': 'File type not allowed'}), 400
        
        # Check file size
        file.seek(0, os.SEEK_END)
        file_size = file.tell()
        file.seek(0)
        
        if file_size > MAX_FILE_SIZE:
            return jsonify({'error': 'File size too large (max 50MB)'}), 400
        
        # Generate unique filename
        original_filename = secure_filename(file.filename)
        file_extension = original_filename.rsplit('.', 1)[1].lower()
        unique_filename = f"{uuid.uuid4().hex}_{original_filename}"
        
        # Determine file type and set S3 key
        file_type = get_file_type(original_filename)
        s3_key = f"{file_type}s/{unique_filename}"  # e.g., images/abc123_bird.jpg
        print(s3_key)
        # Upload to S3
        try:
            s3_client.upload_fileobj(
                file,
                S3_BUCKET,
                s3_key,
                ExtraArgs={
                    'ContentType': file.content_type,
                    'Metadata': {
                        'original_filename': original_filename,
                        'uploaded_by': session.get('user', ''),
                        'upload_time': datetime.now().isoformat(),
                        'file_type': file_type
                    }
                }
            )
            
            # Generate S3 URL
            s3_url = f"https://{S3_BUCKET}.s3.{S3_REGION}.amazonaws.com/{s3_key}"
            print(s3_url)
            
            return jsonify({
                'success': True,
                'message': 'File uploaded successfully',
                'filename': unique_filename,
                'original_filename': original_filename,
                's3_url': s3_url,
                's3_key': s3_key,
                'file_type': file_type,
                'file_size': file_size
            }), 200
            
        except Exception as e:
            return jsonify({'error': f'Failed to upload to S3: {str(e)}'}), 500
    
    except Exception as e:
        return jsonify({'error': f'Upload failed: {str(e)}'}), 500

# Add these routes to your existing app.py

@app.route('/api/subscribe', methods=['POST'])
@require_auth
def api_subscribe():
    """API endpoint to subscribe user to bird species notifications"""
    try:
        data = request.get_json()
        email = data.get('email')
        species = data.get('species', '').lower().strip()
        print(email, species)
        # Validate inputs
        if not email or not species:
            return jsonify({
                'success': False,
                'error': 'Email and species are required'
            }), 400
        
        # Validate email matches session user
        if email != session.get('user'):
            return jsonify({
                'success': False,
                'error': 'Email must match logged-in user'
            }), 403
        
        # Call Lambda function for subscription
        lambda_client = boto3.client('lambda', 'us-east-1')
        
        # Prepare payload for Lambda
        lambda_payload = {
            'body': json.dumps({
                'email': email,
                'species': species
            })
        }
        
        # Invoke subscription Lambda function
        response = lambda_client.invoke(
            FunctionName='SNS-notif',  # Replace with your actual Lambda function name
            InvocationType='RequestResponse',
            Payload=json.dumps(lambda_payload)
        )
        
        # Parse Lambda response
        lambda_response = json.loads(response['Payload'].read().decode('utf-8'))
        lambda_body = json.loads(lambda_response.get('body', '{}'))
        
        if lambda_response.get('statusCode') == 200 and lambda_body.get('success'):
            return jsonify({
                'success': True,
                'message': f'Successfully subscribed to {species} notifications',
                'species': species,
                'email': email
            }), 200
        else:
            return jsonify({
                'success': False,
                'error': lambda_body.get('error', 'Subscription failed')
            }), 500
            
    except Exception as e:
        print(f"Error in subscription API: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Subscription failed: {str(e)}'
        }), 500

# Alternative direct SNS subscription (if you prefer not to use Lambda)
@app.route('/api/subscribe-direct', methods=['POST'])
@require_auth
def api_subscribe_direct():
    """Direct SNS subscription without Lambda"""
    try:
        data = request.get_json()
        email = data.get('email')
        species = data.get('species', '').lower().strip()
        
        # Validate inputs
        if not email or not species:
            return jsonify({
                'success': False,
                'error': 'Email and species are required'
            }), 400
        
        # Validate email matches session user
        if email != session.get('user'):
            return jsonify({
                'success': False,
                'error': 'Email must match logged-in user'
            }), 403
        
        # Create SNS client
        sns_client = get_boto3_client('sns', 'us-east-1')
        
        # Get AWS account ID
        sts_client = get_boto3_client('sts', 'us-east-1')
        account_id = sts_client.get_caller_identity()['Account']
        
        # Create topic name and ARN
        topic_name = f"bird-{species}-notifications"
        topic_arn = f"arn:aws:sns:us-east-1:{account_id}:{topic_name}"
        
        # Create topic if it doesn't exist
        try:
            sns_client.create_topic(Name=topic_name)
        except Exception as topic_error:
            print(f"Topic creation warning: {topic_error}")
        
        # Subscribe user to the topic
        response = sns_client.subscribe(
            TopicArn=topic_arn,
            Protocol='email',
            Endpoint=email
        )
        
        return jsonify({
            'success': True,
            'message': f'Successfully subscribed to {species} notifications. Please check your email to confirm the subscription.',
            'species': species,
            'email': email,
            'subscription_arn': response.get('SubscriptionArn')
        }), 200
        
    except Exception as e:
        print(f"Error in direct subscription: {str(e)}")
        return jsonify({
            'success': False,
            'error': f'Subscription failed: {str(e)}'
        }), 500


@app.route('/logout')
def logout():
    session.clear()
    return redirect(url_for('login'))

if __name__ == '__main__':
    app.run(debug=True)

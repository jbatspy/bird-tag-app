#!/usr/bin/env python3
"""
Load AWS credentials from .env file and set them up
"""

import os

def setup_credentials():
    """Load credentials from .env file into environment"""
    
    # Check if .env exists
    if not os.path.exists('.env'):
        print("❌ .env file not found!")
        return False
    
    # Read .env file
    try:
        with open('.env', 'r') as f:
            lines = f.readlines()
        
        credentials_set = 0
        
        # Parse and set environment variables
        for line in lines:
            line = line.strip()
            if line and not line.startswith('#') and '=' in line:
                key, value = line.split('=', 1)
                key = key.strip()
                value = value.strip()
                
                if key in ['AWS_ACCESS_KEY_ID', 'AWS_SECRET_ACCESS_KEY', 'AWS_SESSION_TOKEN']:
                    os.environ[key] = value
                    print(f"✅ Set {key}")
                    credentials_set += 1
        
        if credentials_set == 3:
            print("✅ All AWS credentials loaded successfully!")
            print("🚀 Ready to run Flask app!")
            return True
        else:
            print(f"⚠️  Only {credentials_set}/3 credentials found")
            return False
            
    except Exception as e:
        print(f"❌ Error reading .env: {str(e)}")
        return False

def test_credentials():
    """Quick test of the credentials"""
    try:
        import boto3
        
        s3 = boto3.client('s3', region_name='us-east-1')
        response = s3.list_buckets()
        print("✅ Credentials working!")
        return True
        
    except Exception as e:
        if 'ExpiredToken' in str(e):
            print("❌ Credentials expired - update your .env file")
        else:
            print(f"❌ Credential test failed: {str(e)}")
        return False

if __name__ == "__main__":
    print("🔧 Setting up AWS credentials...")
    
    if setup_credentials():
        print("\n🧪 Testing credentials...")
        if test_credentials():
            print("\n🎉 All good! Run your Flask app with: python app.py")
        else:
            print("\n💡 Update your .env file with fresh AWS Academy credentials")
    else:
        print("\n💡 Make sure your .env file has all three AWS credentials")
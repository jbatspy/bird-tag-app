# Use AWS Lambda Python 3.11 base image
FROM public.ecr.aws/lambda/python:3.11

# Avoid Matplotlib writing to read-only home
ENV MPLCONFIGDIR=/tmp

# Install system dependencies including build tools
RUN yum install -y \
    gcc \
    gcc-c++ \
    make \
    mesa-libGL \
    mesa-libGLU \
    libSM \
    libXext \
    libXrender \
    && yum clean all

# Set working directory
WORKDIR /var/task

# Upgrade pip first
RUN pip install --upgrade pip

# Copy and install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code and model into the image
COPY file_based_search.py .
COPY model.pt ./model.pt

# Define the Lambda handler
CMD ["file_based_search.lambda_handler"]
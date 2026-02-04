FROM public.ecr.aws/lambda/python:3.11

# Install system libraries for OpenCV and compilers for fallback (if needed)
RUN yum install -y \
    mesa-libGL \
    libSM \
    libXext \
    libXrender \
    gcc \
    gcc-c++ \
    make \
    && yum clean all

# Set working directory
WORKDIR /var/task

# Copy model and application files
COPY model.pt /var/task/model.pt
COPY lambda_detect_img.py .
COPY requirements.txt .

# Install dependencies with binary-only policy
RUN pip install --upgrade pip \
    && pip install --only-binary=:all: --no-cache-dir -r requirements.txt

# Lambda handler
CMD ["lambda_detect_img.lambda_handler"]

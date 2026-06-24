# Container image for running the webscraper on AWS Lambda.
# Uses the official AWS Lambda Python base image (Amazon Linux based), which
# ships the Lambda Runtime Interface Client so the handler "just works".

FROM public.ecr.aws/lambda/python:3.12

# 1. Install Python dependencies into the Lambda task root.
COPY requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# 2. Copy application code.
COPY run.py lambda_handler.py scrapy.cfg ${LAMBDA_TASK_ROOT}/
COPY webscraper/ ${LAMBDA_TASK_ROOT}/webscraper/

# 3. The handler the Lambda runtime will call.
CMD ["lambda_handler.handler"]

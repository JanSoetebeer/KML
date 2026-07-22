# Container image for running the webscraper (with the Modulhandbuch classifier)
# on AWS Lambda. Uses the official AWS Lambda Python base image (Amazon Linux
# based), which ships the Lambda Runtime Interface Client so the handler works.
#
# IMPORTANT: build from the REPO ROOT so the mlclassifier package + trained model
# (which live outside webscraper/) are in the build context:
#
#   docker build -f webscraper/Dockerfile -t <ecr-uri>:latest .
#
FROM public.ecr.aws/lambda/python:3.12

# 1. Python dependencies. webscraper/requirements.txt already includes the ML
#    stack (scikit-learn, pandas, joblib, PyMuPDF), so one install covers both
#    the scraper and the classifier.
COPY webscraper/requirements.txt ${LAMBDA_TASK_ROOT}/
RUN pip install --no-cache-dir -r ${LAMBDA_TASK_ROOT}/requirements.txt

# 2. Scraper application code.
COPY webscraper/run.py webscraper/lambda_handler.py webscraper/scrapy.cfg ${LAMBDA_TASK_ROOT}/
COPY webscraper/webscraper/ ${LAMBDA_TASK_ROOT}/webscraper/

# 3. Classifier package + trained model. Placed under LAMBDA_TASK_ROOT (which is
#    on sys.path), so `import mlclassifier` works and the default model path
#    (mlclassifier/artifacts/module_classifier.joblib) resolves here.
COPY mlclassifier/ ${LAMBDA_TASK_ROOT}/mlclassifier/

# 4. The handler the Lambda runtime will call.
CMD ["lambda_handler.handler"]

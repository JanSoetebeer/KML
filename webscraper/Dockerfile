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

# Optional: OCR of scanned PDFs during the crawl (OCR_ENABLED=true). The Python
# side (pytesseract/Pillow) is installed above; OCR also needs the tesseract
# binary + German language pack. Uncomment to bake it in (adds ~150 MB). The
# base image is Amazon Linux 2023, so use dnf. Left off by default — the batch
# recovery (mlclassifier/reprocess_ocr.py) normally runs locally, and OCR stays a
# no-op without these, so the build is unaffected.
# RUN dnf install -y tesseract tesseract-langpack-deu && dnf clean all

# 2. Scraper application code. bulk_run.py is the Fargate/ECS bulk entrypoint —
#    the ECS task definition overrides the container entrypoint to
#    `python bulk_run.py`, bypassing the Lambda runtime interface below.
COPY webscraper/run.py webscraper/bulk_run.py webscraper/lambda_handler.py webscraper/scrapy.cfg ${LAMBDA_TASK_ROOT}/
COPY webscraper/webscraper/ ${LAMBDA_TASK_ROOT}/webscraper/

# 3. Classifier package + trained model. Placed under LAMBDA_TASK_ROOT (which is
#    on sys.path), so `import mlclassifier` works and the default model path
#    (mlclassifier/artifacts/module_classifier.joblib) resolves here.
COPY mlclassifier/ ${LAMBDA_TASK_ROOT}/mlclassifier/

# 4. The handler the Lambda runtime will call.
CMD ["lambda_handler.handler"]

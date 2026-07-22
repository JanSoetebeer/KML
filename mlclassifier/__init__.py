"""
Modulhandbuch document classifier.

A standalone, TF-IDF + linear baseline for binary document classification:

    1 = Modulhandbuch (module handbook)
    0 = kein Modulhandbuch

The package is intentionally decoupled from the Scrapy webscraper so it can be
trained and evaluated on a folder of labelled PDFs on its own. Integration into
the scraper pipeline / webapp is a separate, later step that only needs the
saved model artifact and :func:`mlclassifier.predict.classify_document`.

Entry points
------------
CLI:      ``python -m mlclassifier {build-dataset|train|predict} ...``
Library:  ``from mlclassifier.predict import load_classifier``
"""

__version__ = "0.1.0"

# Bumped whenever the trained model's feature/labelling contract changes. Stored
# inside every saved artifact so predictions can be traced back to a model.
MODEL_VERSION = "module-classifier-0.1.0"

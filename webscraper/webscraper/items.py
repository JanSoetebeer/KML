import scrapy


class DocumentItem(scrapy.Item):
    """A single downloadable document found during a crawl (document-harvesting
    profiles). Produced by ``ExtractionProfile.extract_target``."""

    url = scrapy.Field()            # Absolute URL of the document
    filename = scrapy.Field()       # Bare filename, e.g. "report.pdf"
    source_page = scrapy.Field()    # URL of the page the link was found on
    file_type = scrapy.Field()      # "pdf", "docx", "doc", etc.
    content = scrapy.Field()        # Raw bytes — populated by download pipeline
    size_bytes = scrapy.Field()     # File size after download
    crawled_at = scrapy.Field()     # ISO-8601 timestamp
    job_id = scrapy.Field()         # Unique run identifier (set in spider)
    extra = scrapy.Field()          # Dict for spider-specific metadata (open extension slot)


class ContentItem(scrapy.Item):
    """Text/content extracted from a crawled HTML page (HTML-content and
    structured-field profiles). Produced by ``ExtractionProfile.extract_page``.

    ``fields`` is an open slot for structured extraction (arbitrary key/value
    pairs a profile pulls from the page); ``text`` holds free-text content.
    """

    url = scrapy.Field()            # Absolute URL of the page
    title = scrapy.Field()          # Page <title> (or a profile-chosen heading)
    text = scrapy.Field()           # Extracted free-text content
    fields = scrapy.Field()         # Dict of structured fields (open slot)
    crawled_at = scrapy.Field()     # ISO-8601 timestamp
    job_id = scrapy.Field()         # Unique run identifier (set in spider)
    extra = scrapy.Field()          # Dict for profile-specific metadata

import scrapy


class DocumentItem(scrapy.Item):
    """Represents a single downloadable document found during a crawl."""

    url = scrapy.Field()            # Absolute URL of the document
    filename = scrapy.Field()       # Bare filename, e.g. "report.pdf"
    source_page = scrapy.Field()    # URL of the page the link was found on
    file_type = scrapy.Field()      # "pdf", "docx", "doc", etc.
    content = scrapy.Field()        # Raw bytes — populated by download pipeline
    size_bytes = scrapy.Field()     # File size after download
    crawled_at = scrapy.Field()     # ISO-8601 timestamp
    job_id = scrapy.Field()         # Unique run identifier (set in spider)
    extra = scrapy.Field()          # Dict for spider-specific metadata (open extension slot)

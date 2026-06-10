import abc
import logging

logger = logging.getLogger(__name__)


class BasePipeline(abc.ABC):
    """
    Interface that all storage pipelines must implement.

    Extension guide
    ---------------
    To add a new storage backend (e.g. a database pipeline):

    1. Create ``webscraper/pipelines/my_pipeline.py``.
    2. Subclass ``BasePipeline``.
    3. Implement :meth:`process_item` (and optionally ``open_spider`` /
       ``close_spider``).
    4. Register it in ``webscraper/settings.py`` under ``ITEM_PIPELINES``
       with an appropriate priority number (lower = runs first).
    """

    @abc.abstractmethod
    def process_item(self, item, spider):
        """
        Persist *item* to the storage backend.

        Must return the item (possibly modified) so that subsequent pipelines
        in the chain continue to receive it.
        """

    def open_spider(self, spider) -> None:
        logger.debug("%s opened for spider '%s'.", self.__class__.__name__, spider.name)

    def close_spider(self, spider) -> None:
        logger.debug("%s closed for spider '%s'.", self.__class__.__name__, spider.name)

"""
Modulhandbuch profile — harvest German university module handbooks.

This is the reference implementation of a keyword-steered document-harvesting
profile: it downloads PDF/DOC/DOCX files and steers the crawl toward
Studiengang / Modulhandbuch pages (and away from news/imprint/mensa) so the
small page budget is spent where the handbooks actually live. Paired with the
trained classifier in :mod:`webscraper.pipelines.classification_pipeline`.

Tune recall by editing the token → weight maps below.
"""

from webscraper.profiles.base import KeywordScoredProfile


class ModulhandbuchProfile(KeywordScoredProfile):
    name = "modulhandbuch"
    target_extensions = frozenset({".pdf", ".doc", ".docx"})
    # Terms handed to the search-discovery stage (webscraper.discovery). Each is
    # combined with the domain + ``filetype:pdf`` into a query. "modulebook"
    # catches English TYPO3 exports (e.g. Konstanz) the crawler otherwise misses.
    discovery_terms = (
        "modulhandbuch", "modulbeschreibung", "modulhandbücher",
        "module handbook", "modulebook", "modulkatalog",
    )

    POSITIVE_TOKENS = {
        "modulhandbuch": 100, "modulhandbuecher": 100, "module-handbook": 100,
        # Real-world filename variants observed in crawl manifests but previously
        # unscored: English TYPO3 exports ("modulebook_19_….pdf", e.g. Konstanz),
        # the "MHB_…"/"…mhb…" abbreviation (Kiel, KIT, many faculties), and the
        # standalone "handbuch_….pdf". Without these, best-first under-prioritises
        # the very links that are handbooks, so a small page/item budget is spent
        # elsewhere before reaching them.
        "modulebook": 100, "mhb": 50, "handbuch": 40, "modul-handbuch": 100,
        "modulbeschreibung": 60, "modulkatalog": 60, "modulubersicht": 40,
        "modul": 25, "module": 20,
        "pruefungsordnung": 35, "studienordnung": 35, "studienplan": 30,
        "studienverlaufsplan": 30, "spo": 15, "stupo": 20,
        "curriculum": 30, "ordnung": 12,
        "studiengang": 20, "studiengaenge": 20, "studium": 15, "studies": 10,
        "bachelor": 15, "master": 15, "b-sc": 10, "m-sc": 10,
        "vorlesungsverzeichnis": 20, "lehrveranstaltung": 12, "lehre": 8,
        "fachbereich": 8, "fakultaet": 8, "institut": 5,
        "download": 10, "downloads": 10, "dokumente": 10, "formulare": 6,
        "pdf": 4,
    }

    NEGATIVE_TOKENS = {
        "aktuelles": -40, "news": -40, "presse": -40, "pressemitteilung": -40,
        "veranstaltung": -30, "event": -30, "termine": -20, "kalender": -20,
        "kontakt": -30, "impressum": -60, "datenschutz": -60, "cookie": -50,
        "mensa": -30, "wohnen": -20, "sport": -20, "hochschulsport": -25,
        "stellenangebot": -30, "karriere": -20, "jobs": -20, "stellen": -20,
        "login": -40, "anmeldung": -20, "suche": -25, "search": -25,
        "sitemap": -20, "rss": -25, "feed": -25,
        "english": -15, "/en/": -15,
        "alumni": -20, "spende": -25, "blog": -20, "gremien": -20,
    }

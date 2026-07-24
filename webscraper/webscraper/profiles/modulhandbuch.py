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

    POSITIVE_TOKENS = {
        "modulhandbuch": 100, "modulhandbuecher": 100, "module-handbook": 100,
        "modulbeschreibung": 60, "modulkatalog": 60,
        "modul": 25, "module": 20,
        "pruefungsordnung": 35, "studienordnung": 35, "studienplan": 30,
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

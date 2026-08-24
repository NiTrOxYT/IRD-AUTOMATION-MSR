import logging
from app.database.db import get_all_sites, add_site
from app.database.models import Site

logger = logging.getLogger("IRD_Seed")

INITIAL_21_SITES = [
    {"name": "FNB", "launcher_button": "FNB", "url": "https://fnb-portal.mymenu.internal"},
    {"name": "Site 02", "launcher_button": "SITE02", "url": "https://site02-portal.mymenu.internal"},
    {"name": "Site 03", "launcher_button": "SITE03", "url": "https://site03-portal.mymenu.internal"},
    {"name": "Site 04", "launcher_button": "SITE04", "url": "https://site04-portal.mymenu.internal"},
    {"name": "Site 05", "launcher_button": "SITE05", "url": "https://site05-portal.mymenu.internal"},
    {"name": "Site 06", "launcher_button": "SITE06", "url": "https://site06-portal.mymenu.internal"},
    {"name": "Site 07", "launcher_button": "SITE07", "url": "https://site07-portal.mymenu.internal"},
    {"name": "Site 08", "launcher_button": "SITE08", "url": "https://site08-portal.mymenu.internal"},
    {"name": "Site 09", "launcher_button": "SITE09", "url": "https://site09-portal.mymenu.internal"},
    {"name": "Site 10", "launcher_button": "SITE10", "url": "https://site10-portal.mymenu.internal"},
    {"name": "Site 11", "launcher_button": "SITE11", "url": "https://site11-portal.mymenu.internal"},
    {"name": "Site 12", "launcher_button": "SITE12", "url": "https://site12-portal.mymenu.internal"},
    {"name": "Site 13", "launcher_button": "SITE13", "url": "https://site13-portal.mymenu.internal"},
    {"name": "Site 14", "launcher_button": "SITE14", "url": "https://site14-portal.mymenu.internal"},
    {"name": "Site 15", "launcher_button": "SITE15", "url": "https://site15-portal.mymenu.internal"},
    {"name": "Site 16", "launcher_button": "SITE16", "url": "https://site16-portal.mymenu.internal"},
    {"name": "Site 17", "launcher_button": "SITE17", "url": "https://site17-portal.mymenu.internal"},
    {"name": "Site 18", "launcher_button": "SITE18", "url": "https://site18-portal.mymenu.internal"},
    {"name": "Site 19", "launcher_button": "SITE19", "url": "https://site19-portal.mymenu.internal"},
    {"name": "Site 20", "launcher_button": "SITE20", "url": "https://site20-portal.mymenu.internal"},
    {"name": "Site 21", "launcher_button": "SITE21", "url": "https://site21-portal.mymenu.internal"},
]

def seed_default_sites_if_empty():
    """Seeds the initial 21 sites if the database has zero sites configured."""
    existing = get_all_sites()
    if existing:
        logger.info(f"Database already contains {len(existing)} sites. Skipping default seed.")
        return

    logger.info("Seeding initial 21 sites into database...")
    for idx, item in enumerate(INITIAL_21_SITES, start=1):
        site = Site(
            name=item["name"],
            launcher_button=item["launcher_button"],
            url=item["url"],
            idp_username="admin@mymenu.local",
            idp_password="ChangeMe123!",
            enabled=True,
            sort_order=idx,
            notes="Default configured site"
        )
        add_site(site)
    logger.info("Successfully seeded 21 initial sites.")

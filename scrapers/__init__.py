from .laprensaaustral import LaPrensaAustralScraper
from .elpinguino import ElPinguinoScraper
from .radiopolar import RadioPolarScraper
from .elmagallanico import ElMagallanicoScraper
from .ovejeronoticias import OvejeroNoticiasScraper
from .sosmagallanes import SosMagallanesScraper
from .radiomagallanes import RadioMagallanesScraper
from .pepenoticias import PepeNoticiasScraper
from .dialogosur import DialogoSurScraper
from .itvpatagonia import ItvPatagoniaScraper
from .zonazero import ZonaZeroScraper

_SCRAPERS = {
    "laprensaaustral": LaPrensaAustralScraper(),
    "elpinguino":      ElPinguinoScraper(),
    "radiopolar":      RadioPolarScraper(),
    "elmagallanico":   ElMagallanicoScraper(),
    "ovejeronoticias": OvejeroNoticiasScraper(),
    "sosmagallanes":   SosMagallanesScraper(),
    "radiomagallanes": RadioMagallanesScraper(),
    "pepenoticias":    PepeNoticiasScraper(),
    "dialogosur":      DialogoSurScraper(),
    "itvpatagonia":    ItvPatagoniaScraper(),
    "zonazero":        ZonaZeroScraper(),
}


def get_scraper(source_id):
    return _SCRAPERS.get(source_id)


__all__ = ["get_scraper", "_SCRAPERS"]

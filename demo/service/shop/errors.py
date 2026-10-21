"""Domain errors. Public functions raise these instead of generic exceptions."""


class ShopError(Exception):
    """Base class for every error this package raises on purpose."""


class UnknownProduct(ShopError):
    """The SKU is not in the catalog."""


class OutOfStock(ShopError):
    """Not enough units in stock."""

from typing import Callable, Any

class LazyProxy:
    """A proxy object that lazily instantiates its target on first attribute access.
    
    Used to defer heavy module-level initializations (like ML models or AWS clients)
    until they are actually needed by a route handler.
    """
    def __init__(self, factory: Callable[[], Any]):
        self._factory = factory
        self._instance = None
    
    def __getattr__(self, name: str) -> Any:
        if self._instance is None:
            self._instance = self._factory()
        return getattr(self._instance, name)

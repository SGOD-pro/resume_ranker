class LazyProxy:
    def __init__(self, factory):
        self._factory = factory
        self._instance = None
    
    def __getattr__(self, name):
        if self._instance is None:
            self._instance = self._factory()
        return getattr(self._instance, name)

class A:
    def __init__(self):
        print("A initialized")
    def say(self):
        print("Hello from A")

a = LazyProxy(A)
print("Before call")
a.say()

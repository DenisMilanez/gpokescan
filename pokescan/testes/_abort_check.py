import threading


class X:
    def __init__(self):
        self._parar = threading.Event()
        self._conectado = True

    def after(self, *a):
        pass

    def _iniciar_varredura(self, n):
        self._parar.clear()

        def run():
            try:
                pass
            finally:
                def restaurar():
                    self.a = "disabled"
                    self.b = ("normal" if self._conectado else "disabled")
                self.after(0, restaurar)
        threading.Thread(target=run, daemon=True).start()

    def _abortar_varredura(self):
        self._parar.set()
        print("Abortando varredura...")

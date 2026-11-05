"""Registro acotado de intentos de Telegram para un único proceso del bot."""
from collections import OrderedDict
from threading import Lock
import time


class RegistroSaturado(Exception):
    """No caben eventos nuevos sin perder protección para eventos recientes."""


class RegistroActualizaciones:
    def __init__(self, capacidad=10000, duracion=24 * 60 * 60):
        if capacidad <= 0 or duracion <= 0:
            raise ValueError("La capacidad y duración del registro deben ser positivas.")
        self.capacidad = capacidad
        self.duracion = duracion
        self._intentos = OrderedDict()
        self._lock = Lock()

    def aceptar(self, update_id):
        """Reserva el ID antes de cualquier efecto; no se libera si el intento falla."""
        if type(update_id) is not int or update_id < 0:
            raise ValueError("update_id debe ser un entero no negativo.")
        with self._lock:
            ahora = time.monotonic()
            while self._intentos:
                _, registrado = next(iter(self._intentos.items()))
                if ahora - registrado < self.duracion:
                    break
                self._intentos.popitem(last=False)
            if update_id in self._intentos:
                return False
            # No expulsar IDs aún vigentes para admitir nuevos: permitiría repetirlos.
            if len(self._intentos) >= self.capacidad:
                raise RegistroSaturado()
            self._intentos[update_id] = ahora
            return True

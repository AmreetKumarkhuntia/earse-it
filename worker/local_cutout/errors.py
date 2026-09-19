class CutoutError(Exception):
    def __init__(self, code: str, message: str):
        super().__init__(message)
        self.code = code


class Cancelled(CutoutError):
    def __init__(self):
        super().__init__("CANCELLED", "Operation cancelled. Your saved selections are retained.")

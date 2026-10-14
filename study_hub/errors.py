class AppError(Exception):
    def __init__(self, title: str, status: int, detail: str, code: str):
        super().__init__(detail)
        self.title = title
        self.status = status
        self.detail = detail
        self.code = code


class NotFoundError(AppError):
    def __init__(self, detail: str):
        super().__init__("Not Found", 404, detail, "not-found")


class ValidationError(AppError):
    def __init__(self, detail: str):
        super().__init__("Validation Failed", 422, detail, "validation-failed")

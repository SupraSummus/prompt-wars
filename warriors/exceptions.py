class TransientLLMError(Exception):
    """Something that is propably fixable by retrying later"""
    pass


class RateLimitError(TransientLLMError):
    pass

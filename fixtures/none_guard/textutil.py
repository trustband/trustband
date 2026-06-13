"""Text normalization helper (TrustBand demo fixture: crashes on None)."""


def normalize(text):
    """Return the text trimmed and lowercased."""
    return text.strip().lower()

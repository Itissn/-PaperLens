"""PaperLens: small, inspectable retrieval-augmented research assistant."""
import sys
if sys.platform=="win32":
    # Use OS certificate trust, including legitimate organisational roots.
    # No certificate verification is disabled.
    import truststore
    truststore.inject_into_ssl()

"""The spaCy pipeline shared by the parsers.

Only spaCy's tokenizer is needed: skill matching is a PhraseMatcher over tokens,
so "Java" never fires inside "JavaScript". A blank English pipeline loads in
about 0.1 s and has no model to download.
"""

from functools import lru_cache

import spacy
from spacy.language import Language
from spacy.tokenizer import Tokenizer
from spacy.util import compile_infix_regex

# spaCy keeps "Node.js/Express" as one token; split on a slash between words so
# both skills are seen. ("CI/CD" is already split and stays matchable as a phrase.)
SLASH_BETWEEN_WORDS = r"(?<=[\w.+#])/(?=[\w.])"


@lru_cache
def get_nlp() -> Language:
    nlp = spacy.blank("en")
    tokenizer = nlp.tokenizer
    if not isinstance(tokenizer, Tokenizer):  # spaCy types it as any callable
        raise TypeError(f"unexpected tokenizer {type(tokenizer)!r}")
    infixes = [*(nlp.Defaults.infixes or ()), SLASH_BETWEEN_WORDS]
    tokenizer.infix_finditer = compile_infix_regex(infixes).finditer
    # spaCy keeps anything URL-shaped ("Node.js/Express") as one token. Callers mask
    # real URLs before matching, so the URL rule only gets in the way.
    tokenizer.url_match = None
    return nlp

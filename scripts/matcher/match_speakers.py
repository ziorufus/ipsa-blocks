"""
Match B-speech blocks from output_con_legislatura.json to parliamentarians
in elenco-parlamentari.tsv, using legislature-filtered string matching.
"""

import argparse
import csv
import json
import re
import unicodedata
from collections import defaultdict
from difflib import SequenceMatcher

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

DEFAULT_FUZZY_THRESHOLD = 0.85

# ---------------------------------------------------------------------------
# Text normalisation helpers
# ---------------------------------------------------------------------------

def normalize(s):
    """Uppercase, remove accents, normalise punctuation and collapse spaces."""
    s = s or ""
    nfkd = unicodedata.normalize("NFKD", s)
    without_accents = "".join(
        c for c in nfkd if not unicodedata.combining(c)
    )

    # Treat hyphens and apostrophes as spaces so that, for example,
    # SANTA-ROSA matches SANTA ROSA and D'AZEGLIO matches D AZEGLIO.
    without_accents = re.sub(r"[-‐‑‒–—'’‘ʼ]", " ", without_accents)
    return " ".join(without_accents.upper().split())


# ---------------------------------------------------------------------------
# Load TSV
# ---------------------------------------------------------------------------

_PAREN_RE = re.compile(r"\s*\(.*?\)\s*")  # matches parenthetical portions


def detect_leg_col(path):
    """Return the 0-based index of the TSV column named 'legislatura'."""
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t", quotechar='"')
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"TSV file is empty: {path}") from exc

    for i, col in enumerate(header):
        if col.strip().lower() == "legislatura":
            return i

    raise ValueError(f"Column 'legislatura' not found in TSV header: {path}")


def _parse_cognome(raw_cog):
    """
    Return (main, aliases) where main is the cognome without parenthetical,
    and aliases is a list of names extracted from inside parentheses.
    """
    main = _PAREN_RE.sub(" ", raw_cog).strip()
    aliases = re.findall(r"\(([^)]+)\)", raw_cog)
    aliases = [a.strip() for a in aliases if a.strip()]
    return main, aliases


def load_tsv(path, leg_col):
    """
    Return dict: {legislature_short: [entry, ...]}
    Each entry has: persona, nome, cognome (raw), cognome_main (no parens),
                    cognome_aliases (list), cognome_norm, cognome_main_norm.
    Also return a secondary index: {leg: {cognome_norm: [entries]}}

    leg_col: 0-based index of the column containing the legislature URL.
    """
    parl = defaultdict(list)
    min_cols = max(4, leg_col + 1)
    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t", quotechar='"')
        next(reader)  # skip header
        for row in reader:
            if len(row) < min_cols:
                continue
            persona_url, nome, cognome = row[0], row[1], row[2]
            leg_url = row[leg_col]
            if not leg_url.strip():
                continue
            leg_short = leg_url.split("/")[-1]
            main, aliases = _parse_cognome(cognome)
            entry = {
                "persona": persona_url,
                "nome": nome.upper(),
                "cognome": cognome,
                "cognome_main": main.upper(),
                "cognome_main_norm": normalize(main),
                "cognome_aliases": [a.upper() for a in aliases],
                "cognome_aliases_norm": [normalize(a) for a in aliases],
            }
            parl[leg_short].append(entry)

    # Build lookup index: leg → cognome_norm (main + aliases) → [entries]
    index = defaultdict(lambda: defaultdict(list))
    for leg, entries in parl.items():
        for e in entries:
            index[leg][e["cognome_main_norm"]].append(e)
            for alias_norm in e["cognome_aliases_norm"]:
                index[leg][alias_norm].append(e)

    return parl, index


def _empty_person_entry(persona_url):
    """Return a minimal candidate entry for matches where only the URL matters."""
    return {
        "persona": persona_url,
        "nome": "",
        "cognome": "",
        "cognome_main": "",
        "cognome_main_norm": "",
        "cognome_aliases": [],
        "cognome_aliases_norm": [],
    }


def load_nicknames_tsv(path, parl_by_leg):
    """
    Return dict: {legislature_short: {nickname_norm: [entry, ...]}}.

    Nickname TSV columns are: persona, nickname, legislatura.
    When possible, the complete canonical person entry is recovered
    from the parliamentarian TSV, so RDF output can include speakerLabel.
    """
    nicknames = defaultdict(lambda: defaultdict(list))

    persons_by_leg_and_url = {
        legislature: {
            entry["persona"]: entry
            for entry in entries
        }
        for legislature, entries in parl_by_leg.items()
    }

    with open(path, newline="", encoding="utf-8") as f:
        reader = csv.reader(f, delimiter="\t", quotechar='"')
        try:
            header = next(reader)
        except StopIteration as exc:
            raise ValueError(f"TSV file is empty: {path}") from exc

        header_norm = [col.strip().lower() for col in header]
        required = ["persona", "nickname", "legislatura"]
        missing = [col for col in required if col not in header_norm]
        if missing:
            raise ValueError(
                f"Column(s) {', '.join(missing)!r} not found in TSV header: {path}"
            )

        persona_col = header_norm.index("persona")
        nickname_col = header_norm.index("nickname")
        leg_col = header_norm.index("legislatura")
        min_cols = max(persona_col, nickname_col, leg_col) + 1

        for row in reader:
            if len(row) < min_cols:
                continue

            persona_url = row[persona_col].strip()
            nickname = row[nickname_col].strip()
            leg_url = row[leg_col].strip()

            if not persona_url or not nickname or not leg_url:
                continue

            leg_short = leg_url.split("/")[-1]

            canonical_entry = (
                persons_by_leg_and_url
                .get(leg_short, {})
                .get(persona_url)
            )

            if canonical_entry is None:
                entry = _empty_person_entry(persona_url)
            else:
                entry = dict(canonical_entry)

            nicknames[leg_short][normalize(nickname)].append(entry)

    return nicknames


# ---------------------------------------------------------------------------
# Speaker extraction
# ---------------------------------------------------------------------------

# Strings that indicate no identifiable individual speaker.
# These blocks are counted as skipped, not as unmatched people.
SKIP_PATTERNS = re.compile(
    r"""^(?:
        # PRESIDENTE and frequent OCR variants:
        # PRESIDENTE, PRESIDENNE, PRESIDERTE, etc.
        (?:il\s+)?presid[a-zà-ÿ]{3,10}\b

        # MINISTRO and OCR variants such as MINISTRÒ.
        | (?:il\s+|i\s+)?ministr[a-zà-ÿ]*\b
        | capo\s+del\s+governo\b

        # Rapporteurs without an explicit personal name.
        | (?:il\s+|lo\s+stesso\s+)?relatore\b

        # Generic or collective deputies/senators, including OCR variants
        # such as SENATOBE.
        | (?:
              un|uno|una|alcuni|alcune|altri|altre|molti|molte|
              parecchi|parecchie|vari|varii|varie|
              (?:tutti|tutte)(?:\s+(?:i|le))?|i|le
          )\s+
          (?:(?:altro|altra|altri|altre)\s+)?
          (?:deput[a-zà-ÿ]{2,12}|senat[a-zà-ÿ]{2,12})\b

        # Anaphoric or otherwise unidentified parliamentary speakers.
        | lo\s+stesso\s+deputato\b
        | alcuni\s+altri\b

        # Unidentified secretaries.
        | (?:un|uno|una|alcuni|alcune|i|le)\s+
          (?:segretario|segretaria|segretari|segretarie)\b
        | uno\s+dei\s+segretari\b

        # Unidentified members of a government or commission.
        | (?:un|uno|una|alcuni|alcune)\s+membr[oi]\s+
          (?:del\s+governo|della\s+commissione)\b

        # Institutional roles without an explicit personal name.
        | il\s+regio\s+commissario\b
        | il\s+commissario\s+regio\b

        # Collective voices and section labels.
        | (?:una|alcune|altre|varie?|molte?|moltissime|numerose)?
          \s*voc[ei]\b
        | voce\b
        | voci\b
        | sommar[i1]o\b

        # French collective label and non-speech headings.
        | quelques\s+députés\b
        | congedo\s+ai\s+senatori\b

        # Italian sentence starters that cannot be surnames.
        | (?:ora|quanto|che|il\s|la\s|gli\s|lo\s|le\s)\s+
    )""",
    re.IGNORECASE | re.VERBOSE,
)

# Italian name prepositions to strip when trying prefix-less matching.
NAME_PREPOSITIONS = re.compile(
    r"^(di|de|del|della|degli|delle|d'|san|santa|santo)\s+",
    re.IGNORECASE,
)

# The name part alone is a role keyword (no personal name).
ROLE_ONLY = re.compile(
    r"^(ministro|sottosegretario|sotto-segretario|relatore|segretario|"
    r"questore|commissario|prefetto|presidente|capo|generale|ammiraglio|"
    r"consultore|commissione)$",
    re.IGNORECASE,
)

# All-caps role phrases that start the name field.
ROLE_PREFIX_RE = re.compile(
    r"^(MINISTR[A-ZÀ-ÖØ-Ý]*|PRESID[A-ZÀ-ÖØ-Ý]*|"
    r"SOTTOSEGRETARIO|SEGRETARIO\s+(GENERALE\s+)?DEL|CAPO\s+DEL)",
    re.IGNORECASE,
)


def extract_raw_speaker(text):
    """
    Extract the initial uppercase speaker label.

    A period after a complete surname normally closes the label:

        RADICE. A questo punto...  -> RADICE
        ARNULFO. È necessario...   -> ARNULFO

    However, if the surname is followed by one or more dotted initials,
    the initials are retained:

        MICHELINI. G. B. Domanda... -> MICHELINI. G. B
        MICHELINI G. B. Domanda...  -> MICHELINI G. B
        SERRA F. M. Osserva...      -> SERRA F. M
    """
    text = re.sub(r"\*+", "", text or "").strip()

    if not text:
        return None

    source_tokens = text.split()
    parts = []
    initial_re = re.compile(r"^[A-ZÀ-ÖØ-Ý]\.$")

    for index, token in enumerate(source_tokens):
        token = token.strip('()[]{}"“”')

        if not token:
            break

        core = token.rstrip(".,:;")
        letters = [char for char in core if char.isalpha()]

        # Running prose normally contains at least one lowercase letter.
        if not letters or not all(char.isupper() for char in letters):
            break

        parts.append(token)

        # A colon or semicolon always closes the label.
        if token.endswith((":", ";")):
            break

        # A period after a complete surname normally closes the label.
        # Exception: continue when the following token is a dotted initial,
        # e.g. MICHELINI. G. B.
        if token.rstrip(" ,:;").endswith(".") and len(letters) > 1:
            next_token = None
            if index + 1 < len(source_tokens):
                next_token = source_tokens[index + 1].strip('()[]{}"“”')

            if next_token and initial_re.fullmatch(next_token):
                continue

            break

    if not parts:
        return None

    return " ".join(parts).rstrip(".,:;").strip()


def clean_speaker(raw):
    """
    Clean up a raw speaker string and return the candidate name string,
    or None if it should be skipped.
    """
    s = raw

    # Remove markdown bold/italic markers
    s = re.sub(r"\*+", "", s)
    s = s.strip()

    # Remove "Senatore " / "Il Senatore " / "Senatore Segretario" prefixes
    s = re.sub(r"^(il\s+)?senatore(\s+segretario)?\s+", "", s, flags=re.IGNORECASE)
    s = s.strip()

    # Skip if empty or too long to be a speaker label
    if not s or len(s) > 120:
        return None

    # Skip known non-person strings
    if SKIP_PATTERNS.match(s):
        return None

    # Split on comma or colon: part before is the name
    m = re.search(r"[,:]", s)
    if m:
        name_part = s[: m.start()].strip()
    else:
        name_part = s

    name_part = name_part.strip()

    if not name_part:
        return None

    # Skip if the name part is itself a role keyword
    if ROLE_ONLY.match(name_part):
        return None

    # Skip all-caps role phrases
    if ROLE_PREFIX_RE.match(name_part):
        return None

    # Skip if it starts lowercase (running text leaked in)
    if re.match(r"^[a-z]", name_part):
        return None

    # If name_part contains lowercase words (running text mixed in), truncate
    # to the leading name-tokens, stopping at the first lowercase verb/function word.
    # Name particles allowed in middle: de, di, d', del, della, von, san, etc.
    _PARTICLE_RE = re.compile(
        r"^(de|di|d'|del|della|degli|delle|von|san|santa|e|y)$", re.IGNORECASE
    )
    tokens = name_part.split()
    if any(t[0].islower() for t in tokens):
        name_tokens = []
        for tok in tokens:
            if tok[0].isupper() or tok[0] in ("'", '"') or _PARTICLE_RE.match(tok):
                name_tokens.append(tok)
            else:
                break  # hit a lowercase non-particle → stop
        name_part = " ".join(name_tokens).strip() if name_tokens else name_part

    if not name_part:
        return None

    # Skip single-token results that are Italian articles/conjunctions leaking through
    _ITALIAN_ARTICLES = {"IL", "LA", "LO", "LE", "GLI", "I", "UN", "UNA", "ORA",
                         "QUANTO", "CHE", "HO", "HA", "SI", "SE", "SU", "MA"}
    if name_part.upper() in _ITALIAN_ARTICLES:
        return None

    # Skip results that are too short to be a name (likely artifacts)
    if len(name_part) <= 2:
        return None

    return name_part


# ---------------------------------------------------------------------------
# Name tokenisation
# ---------------------------------------------------------------------------

def tokenise_name(name_part):
    """
    Split a cleaned name part into (surname_tokens, nome_tokens).
    All consecutive one-letter tokens at the end are treated as name initials.
    """
    tokens = []
    for token in name_part.upper().split():
        token = re.sub(
            r"^[^A-ZÀ-ÖØ-Ý]+|[^A-ZÀ-ÖØ-Ý'-]+$",
            "",
            token,
        )
        if token:
            tokens.append(token)

    if not tokens:
        return [], []

    nome_initials = []
    while len(tokens) >= 2 and len(tokens[-1]) == 1 and tokens[-1].isalpha():
        nome_initials.insert(0, tokens.pop())

    return tokens, nome_initials


# ---------------------------------------------------------------------------
# Matching
# ---------------------------------------------------------------------------

def _fuzzy_best(query_norm, candidates, fuzzy_threshold):
    best_score, best = 0.0, []
    for p in candidates:
        for key in [p["cognome_main_norm"]] + p["cognome_aliases_norm"]:
            s = SequenceMatcher(None, query_norm, key).ratio()
            if s > best_score:
                best_score = s
                best = [p]
            elif s == best_score and s >= fuzzy_threshold and p not in best:
                best.append(p)
    return best_score, best


def match_name_to_parl(
    name_part,
    legislature,
    parl_by_leg,
    index,
    fuzzy_threshold,
    nicknames_by_leg=None,
):
    """
    Try to match name_part to a parliamentarian in the given legislature.
    Returns a dict with: matched (bool), candidates (list), method (str).
    """
    name_norm = normalize(name_part)

    # --- Helper: deduplicate by persona URL ----------------------------------
    def dedup(lst):
        seen = {}
        for p in lst:
            seen[p["persona"]] = p
        return list(seen.values())

    def filter_by_initials(candidates, initials):
        """
        Filter candidates using the longest usable prefix of the extracted
        name initials.

        The complete sequence is always tried first. If it matches nobody,
        progressively ignore trailing initials, which may actually belong to
        the beginning of the intervention:

            FARINA P A     -> try P A, then P
            MICHELINI G B  -> use G B directly

        Returns (filtered_candidates, number_of_initials_used).
        """
        if not initials:
            return [], 0

        for used_count in range(len(initials), 0, -1):
            wanted = initials[:used_count]
            filtered = dedup([
                p for p in candidates
                if [tok[0] for tok in normalize(p["nome"]).split()][:used_count]
                == wanted
            ])
            if filtered:
                return filtered, used_count

        return [], 0

    if legislature not in parl_by_leg:
        return {"matched": False, "candidates": [], "method": "no_legislature"}

    leg_index = index[legislature]

    def fuzzy_with_exact_nome(possible_nome, possible_cog, method):
        nome_matches = [
            p for p in parl_by_leg[legislature]
            if normalize(p["nome"]) == possible_nome
        ]
        best_score, best = _fuzzy_best(possible_cog, nome_matches, fuzzy_threshold)
        if best_score < fuzzy_threshold:
            return None
        best = dedup(best)
        suffix = "" if len(best) == 1 else "_ambiguous"
        return {"matched": True, "candidates": best,
                "method": f"{method}{suffix}({best_score:.2f})"}

    # --- 1. Exact match on full normalised name ------------------------------
    exact = leg_index.get(name_norm, [])
    if exact:
        exact = dedup(exact)
        tokens, nome_toks = tokenise_name(name_part)
        if len(exact) == 1:
            return {"matched": True, "candidates": exact, "method": "exact_full"}
        if nome_toks:
            filtered, used_initials = filter_by_initials(exact, nome_toks)
            if len(filtered) == 1:
                method = (
                    "exact_full+initial"
                    if used_initials == len(nome_toks)
                    else "exact_full+initial_fallback"
                )
                return {"matched": True, "candidates": filtered,
                        "method": method}
        return {"matched": True, "candidates": exact, "method": "exact_full_ambiguous"}

    # --- 2. Exact match on first token only ----------------------------------
    tokens, nome_toks = tokenise_name(name_part)
    first_norm = normalize(tokens[0]) if tokens else ""
    first_match = dedup(leg_index.get(first_norm, []))
    if first_match:
        if len(tokens) >= 2:
            # Try to use remaining tokens as nome
            possible_nome = normalize(" ".join(tokens[1:]))
            nome_match = [p for p in first_match
                          if normalize(p["nome"]) == possible_nome]
            if len(nome_match) == 1:
                return {"matched": True, "candidates": nome_match,
                        "method": "first_token_cog+nome"}
        if nome_toks:
            filtered, used_initials = filter_by_initials(first_match, nome_toks)
            if len(filtered) == 1:
                method = (
                    "first_token_cog+initial"
                    if used_initials == len(nome_toks)
                    else "first_token_cog+initial_fallback"
                )
                return {"matched": True, "candidates": filtered,
                        "method": method}
        if len(first_match) == 1:
            return {"matched": True, "candidates": first_match,
                    "method": "first_token_cog"}
        # Ambiguous but valid
        return {"matched": True, "candidates": first_match,
                "method": "first_token_cog_ambiguous"}

    # --- 3. Compound cognome: all-but-last = cognome, last = nome ------------
    if len(tokens) >= 2:
        cog_norm = normalize(" ".join(tokens[:-1]))
        nom_norm = normalize(tokens[-1])
        cog_match = dedup(leg_index.get(cog_norm, []))
        if cog_match:
            nome_match = [p for p in cog_match
                          if normalize(p["nome"]) == nom_norm]
            if len(nome_match) == 1:
                return {"matched": True, "candidates": nome_match,
                        "method": "compound_cog+nome"}
            if len(cog_match) == 1:
                return {"matched": True, "candidates": cog_match,
                        "method": "compound_cog"}

    # --- 4. First-token match on both cognome and nome -----------------------
    # Handles "LIBERTINI GESUALDO" matching TSV entry nome="GESUALDO",
    # cognome="LIBERTINI PLUCHINOTTA": first token of cognome = "LIBERTINI",
    # first token of nome = "GESUALDO".
    # Tries both orderings: (tokens[0]=cog_first, tokens[1]=nome_first)
    # and (tokens[0]=nome_first, tokens[1]=cog_first).
    if len(tokens) >= 2:
        for cog_tok, nom_tok in [(tokens[0], tokens[1]), (tokens[1], tokens[0])]:
            cog_tok_norm = normalize(cog_tok)
            nom_tok_norm = normalize(nom_tok)
            ft_matches = dedup([
                p for p in parl_by_leg[legislature]
                if p["cognome_main_norm"].split()
                and normalize(p["nome"]).split()
                and p["cognome_main_norm"].split()[0] == cog_tok_norm
                and normalize(p["nome"]).split()[0] == nom_tok_norm
            ])
            if ft_matches:
                if len(ft_matches) == 1:
                    return {"matched": True, "candidates": ft_matches,
                            "method": "first_token_cog+first_token_nome"}
                return {"matched": True, "candidates": ft_matches,
                        "method": "first_token_cog+first_token_nome_ambiguous"}

    # --- 5. Prefix match: extracted name is a prefix of a TSV cognome --------
    # Handles "MAUROGONATO" matching "MAUROGONATO PESARO",
    # "PETRUCCELLI" matching "PETRUCCELLI DELLA GATTINA", etc.
    # If name initials are present, use only the surname tokens for the prefix
    # lookup and then filter the candidates by the complete initial sequence:
    # "BARBAVARA. G" -> GIUSEPPE BARBAVARA DI GRAVELLONA.
    prefix_query_norm = (
        normalize(" ".join(tokens))
        if nome_toks
        else name_norm
    )
    prefix_matches = dedup([
        p for p in parl_by_leg[legislature]
        if p["cognome_main_norm"].startswith(prefix_query_norm + " ")
    ])
    if prefix_matches:
        if nome_toks:
            filtered, used_initials = filter_by_initials(prefix_matches, nome_toks)
            if len(filtered) == 1:
                method = (
                    "prefix_cog+initial"
                    if used_initials == len(nome_toks)
                    else "prefix_cog+initial_fallback"
                )
                return {"matched": True, "candidates": filtered,
                        "method": method}
            if len(filtered) > 1:
                method = (
                    "prefix_cog+initial_ambiguous"
                    if used_initials == len(nome_toks)
                    else "prefix_cog+initial_fallback_ambiguous"
                )
                return {"matched": True, "candidates": filtered,
                        "method": method}
        if len(prefix_matches) == 1:
            return {"matched": True, "candidates": prefix_matches,
                    "method": "prefix_cog"}
        return {"matched": True, "candidates": prefix_matches,
                "method": "prefix_cog_ambiguous"}

    # --- 5. Strip leading preposition and retry ------------------------------
    # Handles "DI PRAMPERO" → try "PRAMPERO", "DE SAINT-BON" → "SAINT-BON" etc.
    stripped = NAME_PREPOSITIONS.sub("", name_part).strip()
    if stripped and stripped != name_part:
        stripped_norm = normalize(stripped)
        stripped_match = dedup(leg_index.get(stripped_norm, []))
        if stripped_match:
            if len(stripped_match) == 1:
                return {"matched": True, "candidates": stripped_match,
                        "method": "strip_prep+exact"}
            return {"matched": True, "candidates": stripped_match,
                    "method": "strip_prep+ambiguous"}
        # Try prefix on stripped form too
        stripped_prefix = dedup([
            p for p in parl_by_leg[legislature]
            if p["cognome_main_norm"].startswith(stripped_norm + " ")
        ])
        if len(stripped_prefix) == 1:
            return {"matched": True, "candidates": stripped_prefix,
                    "method": "strip_prep+prefix"}

    # --- 6. Full name in nome+cognome order ----------------------------------
    # Handles "MARCO ARTURO VICINI": nome="MARCO ARTURO", cognome="VICINI".
    if len(tokens) >= 2:
        for split_at in range(1, len(tokens)):
            possible_nome = normalize(" ".join(tokens[:split_at]))
            possible_cog = normalize(" ".join(tokens[split_at:]))
            cog_match = dedup(leg_index.get(possible_cog, []))
            if not cog_match:
                continue
            nome_match = [
                p for p in cog_match
                if normalize(p["nome"]) == possible_nome
            ]
            if len(nome_match) == 1:
                return {"matched": True, "candidates": nome_match,
                        "method": "nome+cog"}
            if len(nome_match) > 1:
                return {"matched": True, "candidates": nome_match,
                        "method": "nome+cog_ambiguous"}

    # --- 7. Fuzzy cognome with exact nome -------------------------------------
    # Handles OCR slips like "MICHELENI ALESSANDRO" -> "MICHELINI ALESSANDRO".
    if len(tokens) >= 2:
        for split_at in range(1, len(tokens)):
            cog_then_nome = fuzzy_with_exact_nome(
                normalize(" ".join(tokens[split_at:])),
                normalize(" ".join(tokens[:split_at])),
                "fuzzy_cog+nome",
            )
            if cog_then_nome:
                return cog_then_nome

            nome_then_cog = fuzzy_with_exact_nome(
                normalize(" ".join(tokens[:split_at])),
                normalize(" ".join(tokens[split_at:])),
                "fuzzy_nome+cog",
            )
            if nome_then_cog:
                return nome_then_cog

    # --- 8. Fuzzy fallback ---------------------------------------------------
    all_cands = parl_by_leg[legislature]
    best_score, best = _fuzzy_best(name_norm, all_cands, fuzzy_threshold)
    if best_score >= fuzzy_threshold:
        best = dedup(best)
        method = (f"fuzzy({best_score:.2f})" if len(best) == 1
                  else f"fuzzy_ambiguous({best_score:.2f})")
        return {"matched": True, "candidates": best, "method": method}

    # --- 9. Nickname fallback ------------------------------------------------
    # Nicknames are checked only after all matching methods against the
    # main parliamentarian registry have failed.
    if nicknames_by_leg:
        nickname_match = dedup(
            nicknames_by_leg.get(legislature, {}).get(name_norm, [])
        )
        if nickname_match:
            if len(nickname_match) == 1:
                return {
                    "matched": True,
                    "candidates": nickname_match,
                    "method": "nickname_exact",
                }
            return {
                "matched": True,
                "candidates": nickname_match,
                "method": "nickname_exact_ambiguous",
            }

    return {"matched": False, "candidates": [], "method": "no_match"}


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

def parse_args():
    parser = argparse.ArgumentParser(
        description=(
            "Match B-speech blocks from a JSON file to parliamentarians "
            "from a legislature-aware TSV."
        )
    )
    parser.add_argument("json_path", help="Input JSON path.")
    parser.add_argument("tsv_path", help="Input TSV path.")
    parser.add_argument("output_path", help="Output JSON path.")
    parser.add_argument(
        "--fuzzy-threshold",
        type=float,
        default=DEFAULT_FUZZY_THRESHOLD,
        help=f"Minimum fuzzy matching score (default: {DEFAULT_FUZZY_THRESHOLD}).",
    )
    parser.add_argument(
        "--leg-col",
        type=int,
        help=(
            "0-based index of the TSV column containing the legislature URL. "
            "If omitted, the column named 'legislatura' is used."
        ),
    )
    parser.add_argument(
        "--nicknames-tsv",
        help=(
            "Optional TSV with persona, nickname and legislatura columns. "
            "Nickname matches are checked before the standard matching rules."
        ),
    )
    args = parser.parse_args()
    if not 0 <= args.fuzzy_threshold <= 1:
        parser.error("--fuzzy-threshold must be between 0 and 1.")
    if args.leg_col is not None and args.leg_col < 0:
        parser.error("--leg-col must be a 0-based, non-negative index.")
    return args


def main():
    args = parse_args()
    try:
        leg_col = (
            args.leg_col
            if args.leg_col is not None
            else detect_leg_col(args.tsv_path)
        )
    except ValueError as exc:
        raise SystemExit(f"error: {exc}")

    print("Loading TSV…")
    parl_by_leg, index = load_tsv(args.tsv_path, leg_col=leg_col)
    print(f"  Loaded {sum(len(v) for v in parl_by_leg.values())} entries, "
          f"{len(parl_by_leg)} legislature")

    nicknames_by_leg = None
    if args.nicknames_tsv:
        try:
            print("Loading nicknames TSV…")
            nicknames_by_leg = load_nicknames_tsv(args.nicknames_tsv, parl_by_leg)
        except ValueError as exc:
            raise SystemExit(f"error: {exc}")
        nickname_count = sum(
            len(entries)
            for leg_entries in nicknames_by_leg.values()
            for entries in leg_entries.values()
        )
        print(f"  Loaded {nickname_count} nicknames, "
              f"{len(nicknames_by_leg)} legislature")

    print("Loading JSON…")
    with open(args.json_path, encoding="utf-8") as f:
        pages = json.load(f)
    print(f"  Loaded {len(pages)} pages")

    results = []
    stats = defaultdict(int)

    for page in pages:
        legislature = page.get("legislatura", "")
        for block in page.get("blocks", []):
            # Il modello binario salva la classificazione effettiva
            # nel campo predicted_label. Il campo label contiene invece
            # soltanto l'etichetta fittizia usata per costruire il dataset.
            if block.get("predicted_label") != "B-speech":
                continue

            # I nomi espliciti dei parlanti devono trovarsi nei blocchi
            # testuali, non nelle intestazioni o nei titoli DoTS.
            if (block.get("ocr_category") or "").strip().lower() != "text":
                continue

            text = block.get("text", "")
            raw = extract_raw_speaker(text)
            if raw is None:
                stats["no_dot"] += 1
                continue

            clean = clean_speaker(raw)
            if clean is None:
                stats["skipped"] += 1
                continue

            match = match_name_to_parl(
                clean,
                legislature,
                parl_by_leg,
                index,
                args.fuzzy_threshold,
                nicknames_by_leg,
            )

            entry = {
                "page": page.get("page"),
                "block_seq": block.get("block_seq"),
                "legislatura": legislature,
                "raw_speaker": raw,
                "clean_speaker": clean,
                "matched": match["matched"],
                "method": match["method"],
                "candidates": match["candidates"],
            }
            results.append(entry)

            if match["matched"]:
                stats["matched"] += 1
                if "ambiguous" in match["method"]:
                    stats["ambiguous"] += 1
            else:
                stats["unmatched"] += 1

    print("\n--- Stats ---")
    total = stats["matched"] + stats["unmatched"]
    pct = f" ({100*stats['matched']/total:.1f}%)" if total else ""
    print(f"  B-speech blocks processed : {total}")
    print(f"  Skipped (ruoli/generici)  : {stats['skipped']}")
    print(f"  No dot in text            : {stats['no_dot']}")
    print(f"  Matched                   : {stats['matched']}{pct}")
    print(f"    of which ambiguous      : {stats['ambiguous']}")
    print(f"  Unmatched                 : {stats['unmatched']}")

    with open(args.output_path, "w", encoding="utf-8") as f:
        json.dump(results, f, ensure_ascii=False, indent=2)
    print(f"\nOutput written to {args.output_path}")

    # Summary of unmatched cases
    print("\n--- Unmatched cases ---")
    unmatched = [r for r in results if not r["matched"]]
    for r in unmatched:
        print(
            f"  [{r['legislatura']:10s}] page={r['page']} "
            f"clean={repr(r['clean_speaker'][:50])}"
        )


if __name__ == "__main__":
    main()
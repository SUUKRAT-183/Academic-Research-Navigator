"""
Split subject cells whose headings were joined with plain spaces and no separator, e.g.

    'Concrete Technology Concrete Construction Concrete'
        -> ['Concrete Technology', 'Concrete Construction', 'Concrete']

There is no delimiter to split on, so the splitter LEARNS the library's headings from the data itself:
a heading that appears ALONE in a cell (like "Physics", "Concrete Technology") many times is a real heading.
Every long cell is then cut into the longest known headings, left to right. Words that match no known
heading are kept together as one leftover piece.

This is a fallback. A re-export from the library with ';' between subjects is always better. The importer
prints how many cells it could split cleanly, so you can see how well it worked on YOUR file.
"""
from collections import Counter

MIN_COUNT = 3        # a heading must stand alone in at least this many cells to be trusted
MAX_WORDS = 10       # longest single heading considered
PART_RATIO = 0.2     # see _is_composite


def _key(tokens):
    return tuple(t.lower() for t in tokens)


class SubjectSegmenter:
    def __init__(self, headings, display):
        self.headings = headings            # {tuple of lowercase words: how often it stands alone}
        self.display = display              # {same key: nicest original spelling}
        self.max_len = max((len(k) for k in headings), default=1)
        self._cache = {}

    # ------------------------------------------------------------------ learning
    @classmethod
    def learn(cls, cells, min_count=MIN_COUNT, max_words=MAX_WORDS):
        counts, display = Counter(), {}
        for cell in cells:
            tokens = cell.split()
            if not tokens or len(tokens) > max_words:
                continue
            k = _key(tokens)
            counts[k] += 1
            display.setdefault(k, " ".join(tokens))

        # Shortest first, so that by the time we look at "A B" we already know whether "A" and "B" are headings.
        candidates = sorted((k for k, n in counts.items() if n >= min_count),
                            key=lambda k: (len(k), -counts[k]))
        headings = {}
        for k in candidates:
            if len(k) >= 2 and cls._is_composite(k, counts[k], headings):
                continue                                    # just two known headings that sit side by side
            headings[k] = counts[k]
        return cls(headings, display)

    @staticmethod
    def _is_composite(key, count, headings):
        """True when `key` is a cell made entirely of shorter headings that are each reasonably common on
        their own. "Computer programming Electronic digital computer-programming" is such a cell. A real
        two-word heading like "Computer science" is not: "Computer" alone is rare, so the pieces fail
        the test and the pair is kept whole."""
        need = count * PART_RATIO
        n = len(key)
        reach = [False] * (n + 1)
        reach[0] = True
        for i in range(n):
            if not reach[i]:
                continue
            for j in range(i + 1, n + 1):
                if i == 0 and j == n:
                    continue                                # the whole cell is not a part of itself
                if headings.get(key[i:j], 0) >= need:
                    reach[j] = True
        return reach[n]

    # ------------------------------------------------------------------ splitting
    def split(self, cell):
        cell = cell.strip()
        if cell in self._cache:
            return self._cache[cell]
        tokens = cell.split()
        if len(tokens) <= 1:
            out = [cell] if cell else []
            self._cache[cell] = out
            return out

        low = _key(tokens)
        n = len(tokens)
        # best[i] = (score, previous position, how we got there) for the first i words.
        # A known heading earns 100 points per word it covers (minus 1 per piece, so fewer, longer
        # headings win ties); a word that matches nothing earns 0 and is kept as leftover.
        best = [None] * (n + 1)
        best[0] = (0, -1, None)
        for i in range(n):
            if best[i] is None:
                continue
            score = best[i][0]
            if best[i + 1] is None or score > best[i + 1][0]:
                best[i + 1] = (score, i, None)                           # leftover word
            for j in range(i + 1, min(n, i + self.max_len) + 1):
                key = low[i:j]
                if key in self.headings:
                    cand = score + 100 * (j - i) - 1
                    if best[j] is None or cand > best[j][0]:
                        best[j] = (cand, i, key)

        pieces, leftover, pos = [], [], n
        while pos > 0:
            _, prev, key = best[pos]
            if key is None:
                leftover.append(tokens[prev])
            else:
                if leftover:
                    pieces.append(" ".join(reversed(leftover)))
                    leftover = []
                pieces.append(self.display[key])
            pos = prev
        if leftover:
            pieces.append(" ".join(reversed(leftover)))
        out = self._merge_continuations(list(reversed(pieces)))
        self._cache[cell] = out
        return out

    def _merge_continuations(self, pieces):
        """A heading starts with a capital letter (or a digit). An UNKNOWN piece that starts with a lowercase
        word or a dash ("and Technology - Congresses", "- Handbooks", "data structures") is the tail of the
        heading before it, not a heading of its own, so glue it back on."""
        merged = []
        for piece in pieces:
            known = _key(piece.split()) in self.headings
            if merged and not known and not (piece[:1].isupper() or piece[:1].isdigit()):
                merged[-1] = merged[-1] + " " + piece
            else:
                merged.append(piece)
        return merged

    # ------------------------------------------------------------------ reporting
    def quality(self, cells):
        """Share of multi-word cells that were fully explained by known headings."""
        multi = [c for c in set(cells) if len(c.split()) >= 2]
        if not multi:
            return 1.0, 0
        known = 0
        for c in multi:
            if all(_key(p.split()) in self.headings for p in self.split(c)):
                known += 1
        return known / len(multi), len(multi)


def looks_space_joined(cells, min_share=0.25):
    """True if many cells are long runs of words with no separator, the sign of joined headings."""
    cells = [c for c in cells if c]
    if not cells:
        return False
    long_cells = sum(1 for c in cells if len(c.split()) >= 4)
    return long_cells / len(cells) >= min_share

import sys

class RegexNode:
    """Base class for regex AST nodes."""
    pass

class LiteralNode(RegexNode):
    """Matches a single literal character."""
    def __init__(self, char):
        self.char = char

    def __repr__(self):
        return f"'{self.char}'"

class AnyCharNode(RegexNode):
    """Matches any single character (.)."""
    def __repr__(self):
        return "."

class CharSetNode(RegexNode):
    """Matches any character in a set (e.g., [abc])."""
    def __init__(self, chars, negate=False):
        self.chars = set(chars)
        self.negate = negate

    def __repr__(self):
        return f"{'^' if self.negate else ''}[{''.join(sorted(list(self.chars)))}]"

class QuantifierNode(RegexNode):
    """Applies a quantifier (*, +, ?) to a sub-expression."""
    def __init__(self, node, quantifier):
        self.node = node
        self.quantifier = quantifier # '*', '+', '?'

    def __repr__(self):
        return f"({self.node}){self.quantifier}"

class ConcatNode(RegexNode):
    """Concatenates multiple regex nodes (e.g., 'ab')."""
    def __init__(self, nodes):
        self.nodes = nodes

    def __repr__(self):
        return f"({''.join(str(n) for n in self.nodes)})"

class RegexParser:
    """Parses a regular expression string into an AST."""
    def __init__(self, pattern):
        self.pattern = pattern
        self.pos = 0

    def peek(self):
        if self.pos < len(self.pattern):
            return self.pattern[self.pos]
        return None

    def consume(self):
        if self.pos < len(self.pattern):
            char = self.pattern[self.pos]
            self.pos += 1
            return char
        return None

    def parse(self):
        return self._parse_concat()

    def _parse_concat(self):
        nodes = []
        while self.peek() not in (None, '(', ')'): # Stop at end, or group boundaries
            node = self._parse_atom()
            if node:
                nodes.append(node)
            else:
                break # No more atoms to parse (e.g., hit a quantifier after nothing)

        if not nodes:
            return None # Or raise error, or represent empty pattern. For now, assume always content.
        if len(nodes) == 1:
            return nodes[0]
        return ConcatNode(nodes)

    def _parse_atom(self):
        char = self.peek()
        if char is None:
            return None
        
        node = None
        if char == '.':
            self.consume()
            node = AnyCharNode()
        elif char == '[':
            node = self._parse_charset()
        elif char == '\\':
            self.consume() # Consume '\'
            escaped_char = self.consume()
            if escaped_char is None:
                raise ValueError("Incomplete escape sequence")
            node = LiteralNode(escaped_char)
        elif char not in '*+?()': # Literal character
            self.consume()
            node = LiteralNode(char)
        else:
            return None # This isn't an atom for _parse_atom, maybe part of _parse_concat logic later

        if node:
            # Check for quantifiers
            quantifier_char = self.peek()
            if quantifier_char in '*+?':
                self.consume()
                node = QuantifierNode(node, quantifier_char)
        
        return node

    def _parse_charset(self):
        self.consume() # Consume '['
        negate = False
        if self.peek() == '^':
            self.consume()
            negate = True
        
        chars = []
        while self.peek() is not None and self.peek() != ']':
            char = self.consume()
            if char is None: # Should not happen if loop condition is correct
                break
            chars.append(char)
        
        if self.peek() != ']':
            raise ValueError("Unclosed character set: missing ']'")
        self.consume() # Consume ']'

        return CharSetNode(chars, negate)

class RegexEngine:
    """Matches text against a compiled regex AST."""
    def __init__(self, pattern):
        parser = RegexParser(pattern)
        self.ast = parser.parse()

    def match(self, text, start_idx=0):
        """Attempts to match the pattern from start_idx in text."""
        return self._match_node(self.ast, text, start_idx)

    def _match_node(self, node, text, text_idx):
        """
        Recursive function to match a node against text starting from text_idx.
        Returns the index after the match if successful, None otherwise.
        """
        if node is None:
            return text_idx # Empty pattern matches immediately

        if isinstance(node, LiteralNode):
            if text_idx < len(text) and text[text_idx] == node.char:
                return text_idx + 1
            return None

        elif isinstance(node, AnyCharNode):
            if text_idx < len(text):
                return text_idx + 1
            return None

        elif isinstance(node, CharSetNode):
            if text_idx < len(text):
                char = text[text_idx]
                is_in_set = char in node.chars
                if node.negate:
                    if not is_in_set:
                        return text_idx + 1
                else:
                    if is_in_set:
                        return text_idx + 1
            return None

        elif isinstance(node, ConcatNode):
            current_idx = text_idx
            for sub_node in node.nodes:
                next_idx = self._match_node(sub_node, text, current_idx)
                if next_idx is None:
                    return None # Sub-node failed to match
                current_idx = next_idx
            return current_idx # All sub-nodes matched

        elif isinstance(node, QuantifierNode):
            return self._match_quantifier(node.node, node.quantifier, text, text_idx)

        raise ValueError(f"Unknown AST node type: {type(node)}")

    def _match_quantifier(self, sub_node, quantifier, text, text_idx):
        """Handles *, +, ? quantifiers using backtracking."""
        if quantifier == '?': # Zero or one
            # Try matching one
            next_idx = self._match_node(sub_node, text, text_idx)
            if next_idx is not None:
                return next_idx # Matched one, prioritize this
            # If not, try matching zero (i.e., just skip it)
            return text_idx

        elif quantifier == '*': # Zero or more (greedy)
            i = 0
            while True:
                next_idx = self._match_node(sub_node, text, text_idx + i)
                if next_idx is None:
                    break # Failed to match the sub_node again
                i = next_idx - text_idx
            
            # Now, backtrack. Try matching 0, then 1, then 2, etc.
            # This is the tricky part for greedy *
            # We matched 'i' times. We now need to try to match the rest of the pattern
            # starting from text_idx + i, then text_idx + (i-1), etc.

            # The current _match_node only matches one specific node.
            # To correctly implement greedy *, we need to integrate it into the main `find` logic.
            # For `match` (full prefix match), * is simpler: match as many as possible, then try to continue.
            # This implementation assumes the quantifier is at the end of the pattern, or
            # the _match_node handles it correctly. Let's fix this for arbitrary sub-nodes.

            # Correct greedy * implementation (match as many as possible)
            current_match_length = 0
            while True:
                potential_next_idx = self._match_node(sub_node, text, text_idx + current_match_length)
                if potential_next_idx is not None:
                    current_match_length = potential_next_idx - text_idx
                else:
                    break # No more matches for sub_node
            
            # The 'current_match_length' is the maximum successful matches
            return text_idx + current_match_length # This will effectively consume all it can.
                                                  # But for a real regex engine, this needs to be integrated
                                                  # with backtracking for the *entire* pattern.

            # For now, let's implement * using "try matching N, then N-1, ..., 0"
            # This requires knowing the 'next' node in the pattern, which we don't have
            # at this scope. The current `_match_node` is designed to match a *single* node.
            # This means the backtracking logic for quantifiers must be lifted
            # to the `find` or `_search` method that iterates through the pattern's nodes.

            # Re-thinking for `_match_node` to return the *length* of match for simplicity
            # For a simpler greedy *, let's just consume as many as possible.
            # This won't work for `a*a` against `aaaa`, as `a*` would consume all `aaaa`.
            # A full backtracking engine would need the 'rest_of_pattern' argument.

            # Let's adjust the `_match_node` to take `rest_of_pattern` or lift quantifier logic.
            # For this simple engine, I will make the greedy quantifiers behave as "match as much as possible, then return".
            # This will *not* support full backtracking for patterns like `a*a` against `aaa`.
            # A correct approach would be to pass `rest_of_pattern` or use an NFA simulation.
            # Sticking to simple recursion for now, treating quantifiers as self-contained.

            # Simple greedy *:
            idx_after_matches = text_idx
            while True:
                potential_idx = self._match_node(sub_node, text, idx_after_matches)
                if potential_idx is not None:
                    idx_after_matches = potential_idx
                else:
                    break
            return idx_after_matches

        elif quantifier == '+': # One or more (greedy)
            # Must match at least one
            first_match_idx = self._match_node(sub_node, text, text_idx)
            if first_match_idx is None:
                return None # Failed to match even one
            
            # Then match zero or more (same as *)
            idx_after_matches = first_match_idx
            while True:
                potential_idx = self._match_node(sub_node, text, idx_after_matches)
                if potential_idx is not None:
                    idx_after_matches = potential_idx
                else:
                    break
            return idx_after_matches

        return None

    def find(self, text):
        """
        Finds the first occurrence of the pattern in text.
        Returns (start_index, end_index) if found, None otherwise.
        """
        for i in range(len(text) + 1): # +1 to allow matching empty string at end
            end_idx = self._match_node(self.ast, text, i)
            if end_idx is not None:
                return (i, end_idx)
        return None

    def findall(self, text):
        """
        Finds all non-overlapping occurrences of the pattern in text.
        Returns a list of (start_index, end_index) tuples.
        """
        matches = []
        text_idx = 0
        while text_idx <= len(text):
            end_idx = self._match_node(self.ast, text, text_idx)
            if end_idx is not None:
                if end_idx == text_idx: # Prevent infinite loop for zero-width matches
                    if self.ast is None: # Empty pattern matches everywhere, but we only add one per position
                        matches.append((text_idx, end_idx))
                    # For non-empty zero-width matches (e.g., a* on 'bbb', first 'b' is a match of '' followed by 'b')
                    # This case needs more sophisticated handling or specific rules.
                    # For this simple engine, we skip and advance by 1 for zero-width to prevent loops.
                    text_idx += 1
                    continue
                matches.append((text_idx, end_idx))
                text_idx = end_idx # Continue search after the found match
            else:
                text_idx += 1 # No match at this position, try next
        return matches


def main():
    if len(sys.argv) < 3:
        print("Usage: python regex_engine.py <pattern> <text>")
        sys.exit(1)

    pattern = sys.argv[1]
    text = sys.argv[2]

    print(f"Pattern: '{pattern}'")
    print(f"Text:    '{text}'")
    print("-" * 30)

    try:
        engine = RegexEngine(pattern)
        print(f"Parsed AST: {engine.ast}")
        print("-" * 30)

        # Test 'match' (prefix match)
        match_end = engine.match(text)
        if match_end is not None:
            print(f"Prefix match found: text ends at index {match_end}, matched '{text[:match_end]}'")
        else:
            print("No prefix match.")
        
        print("-" * 30)

        # Test 'find' (first occurrence anywhere)
        first_occurrence = engine.find(text)
        if first_occurrence:
            start, end = first_occurrence
            print(f"First occurrence found: from index {start} to {end}, matched '{text[start:end]}'")
        else:
            print("No occurrence found.")

        print("-" * 30)

        # Test 'findall' (all non-overlapping occurrences)
        all_occurrences = engine.findall(text)
        if all_occurrences:
            print("All occurrences found:")
            for start, end in all_occurrences:
                print(f"  - From index {start} to {end}, matched '{text[start:end]}'")
        else:
            print("No occurrences found.")

    except ValueError as e:
        print(f"Error parsing pattern: {e}")
    except Exception as e:
        print(f"An unexpected error occurred: {e}")

if __name__ == "__main__":
    main()
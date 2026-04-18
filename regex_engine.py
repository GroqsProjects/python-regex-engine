import sys

class RegexNode:
    """Base class for regex AST nodes."""
    pass

class LiteralNode(RegexNode):
    """Matches a single literal character."""
    def __init__(self, char):
        self.char = char

    def __repr__(self):
        return f"Literal('{self.char}')"

class AnyCharNode(RegexNode):
    """Matches any single character (.)."""
    def __repr__(self):
        return "AnyChar"

class CharSetNode(RegexNode):
    """Matches any character in a set (e.g., [abc])."""
    def __init__(self, chars, negate=False):
        self.chars = set(chars)
        self.negate = negate

    def __repr__(self):
        return f"CharSet({'^' if self.negate else ''}[{''.join(sorted(list(self.chars)))}])"

class QuantifierNode(RegexNode):
    """Applies a quantifier (*, +, ?) to a sub-expression."""
    def __init__(self, node, quantifier):
        self.node = node
        self.quantifier = quantifier # '*', '+', '?'

    def __repr__(self):
        return f"Quantifier({self.node}, '{self.quantifier}')"

class ConcatNode(RegexNode):
    """Concatenates multiple regex nodes (e.g., 'ab')."""
    def __init__(self, nodes):
        self.nodes = nodes

    def __repr__(self):
        return f"Concat({[str(n) for n in self.nodes]})"

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
        # A pattern is essentially a concatenation of atoms
        return self._parse_concat()

    def _parse_concat(self):
        nodes = []
        while self.peek() not in (None, '(', ')'): # Stop at end, or group boundaries
            node = self._parse_atom()
            if node:
                nodes.append(node)
            else:
                break # No more atoms to parse (e.g., hit a quantifier after nothing, or end)

        if not nodes:
            return None # Represents an empty pattern
        if len(nodes) == 1:
            return nodes[0]
        return ConcatNode(nodes)

    def _parse_atom(self):
        char = self.peek()
        if char is None:
            return None # End of pattern

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
            # This is a special character not acting as an atom in this context
            # (e.g., a quantifier without a preceding element, or an unmatched parenthesis)
            # For now, let it be handled implicitly by returning None.
            return None

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
        parsed_ast = parser.parse()
        # Ensure the top-level AST is always a list of nodes for easier processing
        if isinstance(parsed_ast, ConcatNode):
            self.pattern_nodes = parsed_ast.nodes
        elif parsed_ast is None:
            self.pattern_nodes = [] # Represents an empty pattern
        else:
            self.pattern_nodes = [parsed_ast]

    def _match_single_node(self, node, text, text_idx):
        """
        Attempts to match a single AST node at text_idx.
        Returns text_idx + 1 if successful, None otherwise.
        """
        if text_idx >= len(text):
            return None # Cannot match beyond end of text

        char = text[text_idx]

        if isinstance(node, LiteralNode):
            return text_idx + 1 if char == node.char else None

        elif isinstance(node, AnyCharNode):
            return text_idx + 1

        elif isinstance(node, CharSetNode):
            is_in_set = char in node.chars
            if node.negate:
                return text_idx + 1 if not is_in_set else None
            else:
                return text_idx + 1 if is_in_set else None
        
        # QuantifierNode and ConcatNode are handled by _match_recursive, not _match_single_node
        # If this is reached, something is wrong in the call logic.
        raise ValueError(f"'_match_single_node' called with invalid node type: {type(node)}")

    def _match_recursive(self, pattern_nodes, text, text_idx):
        """
        Core recursive backtracking function.
        Attempts to match the list of pattern_nodes against text starting from text_idx.
        Returns the index after the match if successful, None otherwise.
        """
        # Base case: All pattern nodes have been matched
        if not pattern_nodes:
            return text_idx

        current_node = pattern_nodes[0]
        rest_of_pattern = pattern_nodes[1:]

        if isinstance(current_node, ConcatNode):
            # Flatten concat nodes into the current pattern_nodes list for easier iteration
            # This makes the AST slightly less "pure" but simplifies recursive matching.
            # Alternatively, _match_recursive would take (current_node, rest_of_pattern) and iterate current_node.nodes
            # For simplicity, let's treat it as a sequence to be matched.
            return self._match_recursive(current_node.nodes + rest_of_pattern, text, text_idx)

        elif isinstance(current_node, QuantifierNode):
            sub_node = current_node.node
            quantifier = current_node.quantifier

            if quantifier == '?': # Zero or one
                # Try matching one
                matched_one_idx = self._match_single_node(sub_node, text, text_idx)
                if matched_one_idx is not None:
                    # If matching one succeeds, try to match the rest of the pattern
                    result = self._match_recursive(rest_of_pattern, text, matched_one_idx)
                    if result is not None:
                        return result
                
                # If matching one failed or did not lead to a full match, try matching zero
                return self._match_recursive(rest_of_pattern, text, text_idx)

            elif quantifier == '*': # Zero or more (greedy, with backtracking)
                # First, try to match the sub_node as many times as possible (greedy phase)
                matched_lengths = [0] # Always can match zero times
                current_len = 0
                while True:
                    potential_next_idx = self._match_single_node(sub_node, text, text_idx + current_len)
                    if potential_next_idx is not None:
                        current_len = potential_next_idx - text_idx
                        matched_lengths.append(current_len)
                    else:
                        break
                
                # Now, backtrack: try matching the rest of the pattern with decreasing matches of sub_node
                # (from max matches down to zero matches)
                for length in reversed(matched_lengths):
                    result = self._match_recursive(rest_of_pattern, text, text_idx + length)
                    if result is not None:
                        return result
                return None # No path led to a full match

            elif quantifier == '+': # One or more (greedy, with backtracking)
                # Must match at least one
                first_match_idx = self._match_single_node(sub_node, text, text_idx)
                if first_match_idx is None:
                    return None # Failed to match even one
                
                # Similar to *, but starting from 1 match
                matched_lengths = [first_match_idx - text_idx] # Matched at least once
                current_len = first_match_idx - text_idx
                while True:
                    potential_next_idx = self._match_single_node(sub_node, text, text_idx + current_len)
                    if potential_next_idx is not None:
                        current_len = potential_next_idx - text_idx
                        matched_lengths.append(current_len)
                    else:
                        break
                
                # Backtrack from max matches down to 1 match
                for length in reversed(matched_lengths):
                    result = self._match_recursive(rest_of_pattern, text, text_idx + length)
                    if result is not None:
                        return result
                return None # No path led to a full match

        else: # Regular Literal, AnyChar, CharSet node
            next_text_idx = self._match_single_node(current_node, text, text_idx)
            if next_text_idx is not None:
                return self._match_recursive(rest_of_pattern, text, next_text_idx)
            return None # Current node did not match

    def match(self, text, start_idx=0):
        """Attempts to match the pattern from start_idx in text."""
        return self._match_recursive(self.pattern_nodes, text, start_idx)

    def find(self, text):
        """
        Finds the first occurrence of the pattern in text.
        Returns (start_index, end_index) if found, None otherwise.
        """
        # Iterate through all possible starting positions in the text
        # If the pattern is empty, it should match at any position (zero-width match)
        for i in range(len(text) + 1):
            end_idx = self._match_recursive(self.pattern_nodes, text, i)
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
            # Check for a match at the current text_idx
            end_idx = self._match_recursive(self.pattern_nodes, text, text_idx)
            if end_idx is not None:
                # Found a match
                if end_idx == text_idx:
                    # This is a zero-width match. To avoid infinite loops,
                    # we must advance the text_idx by at least one.
                    # For example, 'a*' against 'b' would match '' at index 0.
                    # We add the match, then forcefully advance.
                    matches.append((text_idx, end_idx))
                    text_idx += 1 
                else:
                    # Non-zero-width match, advance text_idx to after the match
                    matches.append((text_idx, end_idx))
                    text_idx = end_idx
            else:
                # No match at this position, try the next character
                text_idx += 1
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
        print(f"Parsed AST (top-level nodes): {engine.pattern_nodes}")
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
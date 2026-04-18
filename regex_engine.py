import sys
import string

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
        # Ensure chars is always a set for efficient lookup
        self.chars = set(chars)
        self.negate = negate

    def __repr__(self):
        # For readability, represent a subset if too large, or special names
        if self.negate:
            if self.chars == set(string.digits):
                return "CharSet('\\D')"
            # ... add more special cases if desired for negated sets
            return f"CharSet(NOT {''.join(sorted(list(self.chars)))})"
        else:
            if self.chars == set(string.digits):
                return "CharSet('\\d')"
            if self.chars == set(string.ascii_letters + string.digits + '_'):
                return "CharSet('\\w')"
            if self.chars == set(string.whitespace):
                return "CharSet('\\s')"
            return f"CharSet([{''.join(sorted(list(self.chars)))}])"

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

class AlternationNode(RegexNode):
    """Represents 'OR' logic (e.g., 'a|b')."""
    def __init__(self, alternatives):
        self.alternatives = alternatives # List of RegexNodes, each representing an alternative
    
    def __repr__(self):
        return f"Alternation({[str(n) for n in self.alternatives]})"

class GroupNode(RegexNode):
    """Represents a grouped expression (e.g., '(abc)')."""
    def __init__(self, node):
        self.node = node # The single RegexNode representing the content of the group
    
    def __repr__(self):
        return f"Group({self.node})"

class StartAnchorNode(RegexNode):
    """Matches the beginning of the string (^)."""
    def __repr__(self):
        return "StartAnchor"

class EndAnchorNode(RegexNode):
    """Matches the end of the string ($)."""
    def __repr__(self):
        return "EndAnchor"

# Pre-defined character sets for escapes
DIGITS = set(string.digits)
WORD_CHARS = set(string.ascii_letters + string.digits + '_')
WHITESPACE_CHARS = set(string.whitespace)


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
        # Top-level parsing: handle anchors if present
        nodes = []
        if self.peek() == '^':
            self.consume()
            nodes.append(StartAnchorNode())

        # Parse the main expression (alternation is lowest precedence)
        main_expr = self._parse_alternation()
        if main_expr:
            nodes.append(main_expr)

        if self.peek() == '$':
            self.consume()
            nodes.append(EndAnchorNode())
        
        if self.peek() is not None:
            raise ValueError(f"Unexpected character at end of pattern: '{self.peek()}'")

        if not nodes:
            return None # Represents an empty pattern

        # If it's just one node, return it. Otherwise, wrap in a ConcatNode.
        if len(nodes) == 1:
            return nodes[0]
        return ConcatNode(nodes)

    def _parse_alternation(self):
        # An alternation is a sequence of concatenations separated by '|'
        alternatives = [self._parse_concat()]

        while self.peek() == '|':
            self.consume() # Consume '|'
            alternative = self._parse_concat()
            if alternative is None: # e.g., "a|" or "a||b"
                # An empty alternative is valid, it matches the empty string
                alternatives.append(ConcatNode([]))
            else:
                alternatives.append(alternative)
        
        if len(alternatives) == 1:
            return alternatives[0]
        return AlternationNode(alternatives)

    def _parse_concat(self):
        nodes = []
        # Concatenation stops at end, '|' (handled by _parse_alternation), or ')' (group end)
        # Anchors ^ $ are handled at the top level
        while self.peek() not in (None, '|', ')', '^', '$'):
            node = self._parse_atom()
            if node:
                nodes.append(node)
            else:
                break # No more atoms to parse (e.g., hit an invalid char, or end)

        if not nodes:
            return None # Represents an empty concatenation (matches empty string)
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
        elif char == '(':
            node = self._parse_group()
        elif char == '\\':
            self.consume() # Consume '\'
            escaped_char = self.consume()
            if escaped_char is None:
                raise ValueError("Incomplete escape sequence at end of pattern")
            
            # Handle character class escapes
            if escaped_char == 'd':
                node = CharSetNode(DIGITS)
            elif escaped_char == 'D':
                node = CharSetNode(DIGITS, negate=True)
            elif escaped_char == 'w':
                node = CharSetNode(WORD_CHARS)
            elif escaped_char == 'W':
                node = CharSetNode(WORD_CHARS, negate=True)
            elif escaped_char == 's':
                node = CharSetNode(WHITESPACE_CHARS)
            elif escaped_char == 'S':
                node = CharSetNode(WHITESPACE_CHARS, negate=True)
            else:
                # Other escaped characters become literals (e.g., \*, \+, \.)
                node = LiteralNode(escaped_char)
        elif char not in '*+?': # Literal character, or other special chars like ')' that end groups
            self.consume()
            node = LiteralNode(char)
        else:
            # This is a special character that cannot start an atom (e.g., an unmatched quantifier, or unescaped anchor inside concat)
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
            if char is None:
                break
            chars.append(char)
        
        if self.peek() != ']':
            raise ValueError("Unclosed character set: missing ']'")
        self.consume() # Consume ']'

        return CharSetNode(chars, negate)

    def _parse_group(self):
        self.consume() # Consume '('
        # Recursively parse the content of the group (can be a full regex expression)
        node_inside_group = self._parse_alternation()
        
        if self.peek() != ')':
            raise ValueError("Unclosed group: missing ')'")
        self.consume() # Consume ')'

        if node_inside_group is None:
            # An empty group "()" matches an empty string, so it's a valid pattern
            # Represent it as a ConcatNode with no nodes.
            return GroupNode(ConcatNode([]))
        
        return GroupNode(node_inside_group)


class RegexEngine:
    """Matches text against a compiled regex AST."""
    def __init__(self, pattern):
        parser = RegexParser(pattern)
        parsed_ast = parser.parse()
        # The top-level AST can now be an AlternationNode, GroupNode, or ConcatNode (if anchors are present)
        # Ensure it's always iterable for _match_recursive
        if parsed_ast is None:
            self.top_level_nodes = []
        elif isinstance(parsed_ast, ConcatNode):
            self.top_level_nodes = parsed_ast.nodes
        else:
            self.top_level_nodes = [parsed_ast]

    def _match_single_char_node(self, node, text, text_idx):
        """
        Attempts to match a single AST node (Literal, AnyChar, CharSet) at text_idx.
        Returns text_idx + 1 if successful, None otherwise.
        """
        if text_idx >= len(text):
            return None # Cannot match beyond end of text for consuming nodes

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
        
        raise ValueError(f"'_match_single_char_node' called with invalid node type: {type(node)}")

    def _match_recursive(self, current_node, text, text_idx, next_pattern_nodes_iter):
        """
        Core recursive backtracking function.
        Attempts to match the current_node and then the subsequent pattern (from next_pattern_nodes_iter)
        against text starting from text_idx.
        
        Returns the index after the *full* match if successful, None otherwise.
        `next_pattern_nodes_iter` is an iterator over the rest of the pattern after `current_node`.
        """
        # --- Handle matching of the current_node itself ---

        if current_node is None:
            # An empty node (e.g., from an empty group or empty pattern segment) effectively matches zero width.
            # Continue to match the rest of the pattern.
            return self._match_next_node(text, text_idx, next_pattern_nodes_iter)
        
        elif isinstance(current_node, StartAnchorNode):
            if text_idx == 0:
                # Start anchor is a zero-width assertion, successfully matched.
                return self._match_next_node(text, text_idx, next_pattern_nodes_iter)
            return None # Failed to match start anchor

        elif isinstance(current_node, EndAnchorNode):
            if text_idx == len(text):
                # End anchor is a zero-width assertion, successfully matched.
                return self._match_next_node(text, text_idx, next_pattern_nodes_iter)
            return None # Failed to match end anchor

        elif isinstance(current_node, LiteralNode) or \
             isinstance(current_node, AnyCharNode) or \
             isinstance(current_node, CharSetNode):
            
            next_text_idx = self._match_single_char_node(current_node, text, text_idx)
            if next_text_idx is not None:
                # If current node matched, try to match the rest of the pattern
                return self._match_next_node(text, next_text_idx, next_pattern_nodes_iter)
            return None # Current node did not match

        elif isinstance(current_node, QuantifierNode):
            sub_node = current_node.node
            quantifier = current_node.quantifier

            if quantifier == '?': # Zero or one
                # Option 1: Try matching one (recursively, as sub_node could be complex)
                matched_one_idx = self._match_recursive(sub_node, text, text_idx, iter([]))
                if matched_one_idx is not None:
                    # If matching one succeeds, try to match the rest of the pattern
                    result = self._match_next_node(text, matched_one_idx, next_pattern_nodes_iter)
                    if result is not None:
                        return result
                
                # Option 2: If matching one failed or did not lead to a full match, try matching zero
                return self._match_next_node(text, text_idx, next_pattern_nodes_iter)

            elif quantifier == '*': # Zero or more (greedy, with backtracking)
                # First, try to match the sub_node as many times as possible (greedy phase)
                matched_indices = [text_idx] # Always can match zero times
                current_temp_idx = text_idx
                while True:
                    # Match sub_node (potentially complex) from current_temp_idx
                    potential_next_idx = self._match_recursive(sub_node, text, current_temp_idx, iter([]))
                    if potential_next_idx is not None and potential_next_idx > current_temp_idx: # Ensure progress for zero-width sub_nodes
                        current_temp_idx = potential_next_idx
                        matched_indices.append(current_temp_idx)
                    else:
                        break
                
                # Now, backtrack: try matching the rest of the pattern with decreasing matches of sub_node
                # (from max matches down to zero matches)
                for idx_to_try in reversed(matched_indices):
                    result = self._match_next_node(text, idx_to_try, next_pattern_nodes_iter)
                    if result is not None:
                        return result
                return None # No path led to a full match

            elif quantifier == '+': # One or more (greedy, with backtracking)
                # Must match at least one
                first_match_idx = self._match_recursive(sub_node, text, text_idx, iter([]))
                if first_match_idx is None:
                    return None # Failed to match even one

                # Similar to *, but starting from 1 match
                matched_indices = [first_match_idx] # Matched at least once
                current_temp_idx = first_match_idx
                while True:
                    potential_next_idx = self._match_recursive(sub_node, text, current_temp_idx, iter([]))
                    if potential_next_idx is not None and potential_next_idx > current_temp_idx: # Ensure progress for zero-width sub_nodes
                        current_temp_idx = potential_next_idx
                        matched_indices.append(current_temp_idx)
                    else:
                        break
                
                # Backtrack from max matches down to 1 match
                for idx_to_try in reversed(matched_indices):
                    result = self._match_next_node(text, idx_to_try, next_pattern_nodes_iter)
                    if result is not None:
                        return result
                return None # No path led to a full match

        elif isinstance(current_node, ConcatNode):
            # A ConcatNode represents a sequence of sub-nodes.
            # We chain its sub-nodes with the rest of the original pattern.
            chained_iterator = iter(current_node.nodes)
            return self._match_next_node(text, text_idx, self._chain_iterators(chained_iterator, next_pattern_nodes_iter))

        elif isinstance(current_node, AlternationNode):
            # Try each alternative in sequence. The first one that leads to a full match wins.
            for alternative_node in current_node.alternatives:
                result = self._match_recursive(alternative_node, text, text_idx, next_pattern_nodes_iter)
                if result is not None:
                    return result
            return None # None of the alternatives led to a match

        elif isinstance(current_node, GroupNode):
            # A GroupNode simply defers to its internal node.
            return self._match_recursive(current_node.node, text, text_idx, next_pattern_nodes_iter)
        
        raise ValueError(f"'_match_recursive' received unknown AST node type: {type(current_node)}")

    def _chain_iterators(self, *iterators):
        """Helper to chain multiple iterators (for ConcatNode chaining)."""
        for it in iterators:
            yield from it

    def _match_next_node(self, text, text_idx, pattern_nodes_iter):
        """
        Helper to get the next node from the iterator and continue matching.
        This allows the recursion to proceed through the pattern sequence.
        """
        try:
            next_node = next(pattern_nodes_iter)
            return self._match_recursive(next_node, text, text_idx, pattern_nodes_iter)
        except StopIteration:
            # If the iterator is exhausted, it means all pattern nodes have matched.
            return text_idx # Successful match, return the current text index


    def match(self, text, start_idx=0):
        """Attempts to match the pattern from start_idx in text."""
        # Wrap the top-level nodes in an iterator for _match_recursive
        top_level_iter = iter(self.top_level_nodes)
        try:
            first_node = next(top_level_iter)
            return self._match_recursive(first_node, text, start_idx, top_level_iter)
        except StopIteration:
            # Empty pattern (or pattern that evaluates to empty, like "()") always matches.
            # In this context (match from start_idx), it's a zero-width match at start_idx.
            return start_idx

    def find(self, text):
        """
        Finds the first occurrence of the pattern in text.
        Returns (start_index, end_index) if found, None otherwise.
        """
        for i in range(len(text) + 1):
            end_idx = self.match(text, i) # Reuse match for finding
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
            end_idx = self.match(text, text_idx)
            if end_idx is not None:
                if end_idx == text_idx:
                    # Zero-width match. Add it, then force advance text_idx by 1 to prevent infinite loop.
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
        # For top_level_nodes, it could be a list of nodes now due to anchors
        print(f"Parsed AST (top-level nodes): {engine.top_level_nodes}")
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
"""Step 1 - Read and parse syntax A scripts from a directory.

The parser is purely lexical (regex + comment stripping), driven by the
language profile. It does not build a full syntax tree: for categorisation
and complexity scoring, counting calls, libraries and control flow is enough,
and it keeps the parser portable to any language.
"""
import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

# String literals are removed before searching for calls, so that
# "print(x)" written inside a string is not counted as a call.
STRING_LITERAL = re.compile(r'"(?:[^"\\]|\\.)*"|\'(?:[^\'\\]|\\.)*\'')


@dataclass
class ParsedScript:
    name: str                      # file name without extension
    path: Path
    source: str                    # full original text (sent to the LLM)
    code_lines: list[str]          # non-empty lines, comments removed
    comments: list[str]            # comment text (business keywords live here)
    function_calls: Counter = field(default_factory=Counter)
    libraries: set[str] = field(default_factory=set)
    control_flow: Counter = field(default_factory=Counter)
    user_functions: int = 0        # functions defined in the script

    @property
    def loc(self) -> int:
        """Lines of code, excluding blank lines and comments."""
        return len(self.code_lines)


def split_comment(line: str, prefix: str) -> tuple[str, str]:
    """Split a line into (code, comment), ignoring the prefix inside strings."""
    quote = None
    for i, char in enumerate(line):
        if quote:
            if char == quote and line[i - 1] != "\\":
                quote = None
        elif char in ("'", '"'):
            quote = char
        elif line.startswith(prefix, i):
            return line[:i], line[i + len(prefix):]
    return line, ""


def parse_script(path: Path, profile: dict) -> ParsedScript:
    source = path.read_text(encoding="utf-8")
    code_lines, comments = [], []
    for raw in source.splitlines():
        code, comment = split_comment(raw, profile["comment_prefix"])
        if code.strip():
            code_lines.append(code.rstrip())
        if comment.strip():
            comments.append(comment.strip())

    code = STRING_LITERAL.sub('""', "\n".join(code_lines))
    keywords = set(profile["control_flow_keywords"])

    calls = Counter(re.findall(profile["function_call_pattern"], code))
    control_flow = Counter({k: calls.pop(k) for k in list(calls) if k in keywords})
    # "else" and "repeat" are not followed by "(", count them separately
    for kw in ("else", "repeat"):
        if kw in keywords:
            control_flow[kw] += len(re.findall(rf"\b{kw}\b", code))
    calls.pop("function", None)  # definitions are counted below, not as calls

    libraries = set(re.findall(profile["library_pattern"], code))
    libraries |= set(re.findall(profile["namespace_pattern"], code))

    return ParsedScript(
        name=path.stem,
        path=path,
        source=source,
        code_lines=code_lines,
        comments=comments,
        function_calls=calls,
        libraries=libraries,
        control_flow=+control_flow,  # unary + drops zero counts
        user_functions=len(re.findall(profile["function_definition_pattern"], code)),
    )


def load_scripts(directory: Path, profile: dict) -> list[ParsedScript]:
    """Parse every script with the profile's extension, sorted by name."""
    paths = sorted(directory.glob(f"*{profile['extension']}"))
    if not paths:
        raise FileNotFoundError(f"No *{profile['extension']} files in {directory}")
    return [parse_script(p, profile) for p in paths]

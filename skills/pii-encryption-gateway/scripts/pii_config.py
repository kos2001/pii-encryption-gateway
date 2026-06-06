"""Which fields count as sensitive, and the token type used for each.

This is the column-name layer of protection. Field names are matched
case-insensitively against both the exact column name and a set of substring
aliases, so the same config works on Korean HR exports whether a column is
called "연봉", "salary", or "기본연봉".

A value still gets protected even when its column name is not listed here:
recognizers.py is a second pass that detects PII by value shape (RRN, phone,
email, account, card) inside any non-classified column, including free-text.
This file controls the *column-name* net; recognizers.py is the value-shape net.

To adapt the gateway to a different dataset, edit SENSITIVE_FIELDS (column
names) and/or add recognizers to recognizers.py (value patterns).
"""

# token_type -> list of column-name aliases (substring, case-insensitive match)
SENSITIVE_FIELDS = {
    "EMPNO": ["사번", "사원번호", "employee_id", "empno", "emp_id"],
    "NAME": ["이름", "성명", "name"],
    "RRN": ["주민등록번호", "주민번호", "rrn", "ssn"],
    "SALARY": ["연봉", "급여", "salary", "pay"],
    "LATE": ["지각", "late"],
    "ABSENCE": ["결근", "absence"],
    "LEAVE": ["연차", "leave", "vacation"],
    "PHONE": ["전화", "휴대폰", "phone", "mobile"],
    "EMAIL": ["이메일", "email", "메일"],
    "ACCOUNT": ["계좌", "account"],
}

# Columns explicitly safe to expose to the LLM (used for grouping/structure).
# Anything not sensitive and not here is also exposed; this list is documentation.
NON_SENSITIVE_HINTS = ["부서", "직급", "입사일", "department", "title"]


def classify_field(column_name: str):
    """Return the token type for a column, or None if it is not sensitive."""
    lowered = column_name.strip().lower()
    for token_type, aliases in SENSITIVE_FIELDS.items():
        for alias in aliases:
            if alias.lower() in lowered:
                return token_type
    return None


# Direct identifiers — fields that point at a specific person. The keyless
# de-identification mode (deidentify.py) tokenizes ONLY these and leaves numeric
# attributes (SALARY, LATE, ABSENCE, LEAVE) raw, so the model can still compute
# aggregates (averages, sums) over them. CARD/BRN/IP are recognizer-only types.
IDENTIFIER_TYPES = {"EMPNO", "NAME", "RRN", "PHONE", "EMAIL", "ACCOUNT", "CARD", "BRN", "IP"}


def classify_identifier(column_name: str):
    """Return the token type only if the column is a DIRECT IDENTIFIER, else None.

    Numeric/analytic sensitive fields (연봉·근태) classify under classify_field
    but are deliberately excluded here so they remain raw for analysis.
    """
    t = classify_field(column_name)
    return t if t in IDENTIFIER_TYPES else None

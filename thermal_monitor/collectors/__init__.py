"""Hardware collectors — each sensor type is its own module.

Design rule: a collector NEVER raises. If a source is unavailable it returns
None / empty list. The UI layer treats None as "N/A" so partial data still works.
"""

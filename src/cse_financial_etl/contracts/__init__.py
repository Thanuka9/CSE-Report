"""Dependency-neutral contracts shared by resolution, validation, publication and release.

Nothing in this package may import from ``facts``, ``validation``, ``extraction``,
``reporting`` or ``tunnels`` — those packages import *from* here.
"""

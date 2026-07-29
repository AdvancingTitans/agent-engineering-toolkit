"""Stable demo error categories and CLI exits."""


class DemoError(Exception):
    exit_code = 1


class DemoUnavailable(DemoError):
    exit_code = 69


class DemoInvariantError(DemoError):
    exit_code = 70


class DemoIOError(DemoError):
    exit_code = 74


class DemoTimeout(DemoError):
    exit_code = 124

"""Greeter application service — short and well named."""

GREETING = "hello"


class Greeter:
    def greet(self, name):
        # build a friendly greeting
        return GREETING + " " + name

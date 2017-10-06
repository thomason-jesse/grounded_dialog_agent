#!/usr/bin/env python
__author__ = 'jesse'


# Perform input/output with the agent through the keyboard.
# This is good for a single user operating with a single instantiated, non-embodied agent.
class KeyboardIO:

    # Takes an instantiated, trained parser, a knowledge base grounder, and an input/output instance.
    def __init__(self):
        pass

    def get_from_user(self):
        print "YOU: "
        u = raw_input()
        return u

    def say_to_user(self, u):
        print "AGENT: " + u

    def perform_action(self, a, p, r):
        if a == 'walk':
            print "ROBOT ACTION: Navigate to location " + p
        elif a == 'bring':
            print "ROBOT ACTION: Pick up item " + p + " and deliver it to person " + p
        else:
            raise ValueError("perform_action: unrecognized action '" + a + "'")

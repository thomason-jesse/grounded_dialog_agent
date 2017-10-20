#!/usr/bin/env python
__author__ = 'jesse'


# Perform input/output with the agent through the keyboard.
# This is good for a single user operating with a single instantiated, non-embodied agent.
class KeyboardIO:

    # Takes an instantiated, trained parser, a knowledge base grounder, and an input/output instance.
    def __init__(self):
        pass

    # Get a string from the user.
    def get_from_user(self):
        print "YOU: "
        u = raw_input()
        return u

    # Get an integer oidx from those provided or None.
    def get_oidx_from_user(self, oidxs):
        print "YOU POINT TO OIDX:"
        while True:  # until return happens
            u = raw_input()
            try:
                ui = int(u)
                if ui in oidxs:
                    return ui
            except ValueError:
                if 'none' in u or 'all' in u:
                    return None

    # Say a string to the user.
    def say_to_user(self, u):
        print "AGENT: " + u

    # Write out what action is taken given an action, patient, and recipient as strings.
    def perform_action(self, a, p, r):
        if a == 'walk':
            print "ROBOT ACTION: Navigate to location " + p
        elif a == 'bring':
            print "ROBOT ACTION: Pick up item " + p + " and deliver it to person " + r
        else:
            raise ValueError("perform_action: unrecognized action '" + a + "'")

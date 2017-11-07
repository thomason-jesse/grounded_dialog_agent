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
        u = None
        while u is None or len(u) == 0:
            u = raw_input()
            u = u.strip()
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

    # Say a string with words aligned to ontological values.
    # u - a string utterance, possibly tagged with role-fill words like <p>this</p>
    # rvs - role values as a dictionary of roles -> strings
    # For KeyboardIO, this simply replaces the tags with the roll-fills and discards the filler text.
    def say_to_user_with_referents(self, u, rvs):
        for r in rvs:
            ts = "<" + r[0] + ">"
            te = "</" + r[0] + ">"
            if ts in u:
                pre_tag = u.split(ts)[0]
                post_tag = u.split(te)[1]
                u = pre_tag + rvs[r] + post_tag
        print "AGENT: " + u

    # Write out what action is taken given an action, patient, and recipient as strings.
    def perform_action(self, a, p, r, s, g):
        if a == 'walk':
            print "ROBOT ACTION: Navigate to location " + g
        elif a == 'bring':
            print "ROBOT ACTION: Pick up item " + p + " and deliver it to person " + r
        elif a == 'move':
            print "ROBOT ACTION: Move item " + p + " from " + s + " to " + g
        else:
            raise ValueError("perform_action: unrecognized action '" + a + "'")

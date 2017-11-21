#!/usr/bin/env python
__author__ = 'jesse'

import os
import time


# Perform input/output with the agent through the keyboard.
# This is good for a single user operating with a single instantiated, non-embodied agent.
class KeyboardIO:

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
    def perform_action(self, rvs):
        if rvs['action'] == 'walk':
            print "ROBOT ACTION: Navigate to location " + rvs['goal']
        elif rvs['action'] == 'bring':
            print "ROBOT ACTION: Pick up item " + rvs['patient'] + " and deliver it to person " + rvs['recipient']
        elif rvs['action'] == 'move':
            print "ROBOT ACTION: Move item " + rvs['patient'] + " from " + rvs['source'] + " to " + rvs['goal']
        else:
            raise ValueError("perform_action: unrecognized action '" + rvs['action'] + "'")


# Perform input/output with the agent through a Sever.
# This is used to facilitate multiple Agents being managed through a central script, such as during
# Mechanical Turk experiments.
class SeverIO:

    # sever - a Server instance to communicate with.
    # id - a numerical id number to pass to the server for identification.
    # spin_time - seconds to spin between polling the server.
    def __init__(self, uid, client_dir, spin_time=1):
        self.uid = uid
        self.client_dir = client_dir
        self.spin_time = spin_time

    # Get a string from the user.
    # Polls the disk until a string message from the user appears.
    # Deletes the string message file from the disk.
    def get_from_user(self):
        path = os.path.join(self.client_dir, self.uid + '.smsgur.txt')  # request
        self._poll_for_file_write_contents(path, ' ')
        print "get_from_user requested feedback"

        path = os.path.join(self.client_dir, self.uid + '.smsgu.txt')
        u = self._poll_for_file_get_contents_delete(path)

        # Preprocess user utterance from the web.
        print "get_from_user (raw): '" + u + "'"
        u = u.lower()
        tks = u.split()
        tks = [tk.strip() for tk in tks]
        to_add = []
        for idx in range(len(tks)):  # replace possession with recognized tokens
            if "'" in tks[idx] and tks[idx][0] != "'":  # contains apostrophe
                if tks[idx][-1] != "s":  # word ends like jess'
                    tks[idx] = tks[idx][:-1]  # cut off apostrophe
                else:  # word ends like jesse's
                    tks[idx] = tks[idx][:-2]  # cut off apostrophe s
                to_add.append([idx + 1, "'s"])
        for aidx in range(len(to_add)):
            idx, tk = to_add[aidx]
            tks.insert(idx + aidx, tk)
        tks = [tk.strip(',?.\"/\\!*&^%$#@()~+-') for tk in tks]
        u = ' '.join(tks)

        print "get_from_user (processed): '" + u + "'"
        return u

    # Get an integer oidx from those provided or None.
    # Polls the disk until an oidx message from the user appears.
    # Assumes that the file equals 'None' or an integer.
    # oidxs - not used in this implementation; insurance trusted from the client side
    def get_oidx_from_user(self, oidxs):
        path = os.path.join(self.client_dir, self.uid + '.omsgur.txt')  # request
        self._poll_for_file_write_contents(path, ' ')
        print "get_oidx_from_user requested feedback"

        path = os.path.join(self.client_dir, self.uid + '.omsgu.txt')
        u = self._poll_for_file_get_contents_delete(path)
        if u == 'None':
            u = None
        else:
            u = int(u)

        print "get_oidx_from_user: " + str(u)
        return u

    # Poll the disk for the specified file (blocking), get its contents and delete it from the disk.
    def _poll_for_file_get_contents_delete(self, fn):
        while not os.path.isfile(fn):
            time.sleep(self.spin_time)
        with open(fn, 'r') as f:
            u = f.read().strip()
        cmd = "rm -f " + fn
        os.system(cmd)
        return u

    # Say a string to the user.
    # This polls the disk until the existing message string is cleared, then writes the given new one.
    def say_to_user(self, u):
        path = os.path.join(self.client_dir, self.uid + '.smsgs.txt')
        self._poll_for_file_write_contents(path, u)
        print "say_to_user: " + str(u)

    # Say a string with words aligned to ontological values.
    # u - a string utterance, possibly tagged with role-fill words like <p>this</p>
    # rvs - role values as a dictionary of roles -> strings
    # This polls the disk until the existing referent message is cleared, then writes the given new one.
    def say_to_user_with_referents(self, u, rvs):
        path = os.path.join(self.client_dir, self.uid + '.rmsgs.txt')
        s = u + '\n' + ';'.join([str(r) + ':' + str(rvs[r]) for r in rvs])
        self._poll_for_file_write_contents(path, s)
        print "say_to_user_with_referents: " + str(u) + " " + str(rvs)

    # Write out what action is taken given an action, patient, and recipient as strings.
    # If the server already has a waiting one of these (which would be weird), poll until it clears.
    def perform_action(self, rvs):
        if rvs['action'] == 'walk':
            a_str = "The robot navigates to <g>here</g>."
        elif rvs['action'] == 'bring':
            a_str = "The robot finds <p>this</p> and delivers it to <r>this person</r>."
        elif rvs['action'] == 'move':
            a_str = "The robot moves <p>this</p> from <s>here</s> to <g>there</g>."
        elif rvs['action'] == 'init_phase':
            a_str = "Thanks!"
        else:
            a_str = "ERROR: unrecognized action for robot"
        path = os.path.join(self.client_dir, self.uid + '.amsgs.txt')
        s = a_str + '\n' + ';'.join([str(r) + ':' + str(rvs[r]) for r in rvs])
        self._poll_for_file_write_contents(path, s)
        print "perform_action: " + str(rvs)

    # Poll the disk for the specified file (blocking), and write it when it doesn't exist.
    def _poll_for_file_write_contents(self, fn, u):
        while os.path.isfile(fn):
            time.sleep(self.spin_time)
        with open(fn, 'w') as f:
            f.write(u)
        cmd = "chmod a+r " + fn
        os.system(cmd)
        return u

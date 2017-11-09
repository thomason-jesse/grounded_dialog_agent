#!/usr/bin/env python
__author__ = 'jesse'

import sys
sys.path.append('../tsp/')  # necessary to import CKYParser from above directory

import argparse
import KBGrounder
import os
import pickle
import subprocess
import time


class Server:

    devnull = open(os.devnull, 'w')

    def __init__(self, grounder_fn, spin_time, cycles_per_user, client_dir):
        self.grounder_fn = grounder_fn
        self.spin_time = spin_time
        self.cycles_per_user = cycles_per_user
        self.client_dir = client_dir

        # State and message information.
        self.users = []  # uids
        self.agents = {}  # from uid -> subprocesses running agents
        self.time_remaining = {}  # from uid -> int

    # Begin to spin forever, checking the disk for relevant communications.
    def spin(self):

        # Spin.
        print "Server: spinning forever..."
        try:
            while True:

                # Walk the filesystem for new inputs from client-side webpage.
                files_to_remove = []  # list of filenames
                for _, _, files in os.walk(self.client_dir):
                    for fn in files:
                        fnp = fn.split('.')
                        if len(fnp) == 3 and fnp[2] == 'txt':

                            # Check for newly-connected users.
                            if fnp[1] == 'newu':
                                uid = int(fnp[0])
                                if uid not in self.users:
                                    print "Server: found new user " + str(uid)

                                    # Spawn a process that instantiates an Agent and starts a ServerIO dialog.
                                    cmd = ["python", "main.py",
                                           "--grounder_fn", self.grounder_fn,
                                           "--io_type", "server",
                                           "--uid", str(uid),
                                           "--client_dir", self.client_dir,
                                           "--spin_time", str(self.spin_time)]
                                    print ("Server: ... executing subprocess " + str(cmd) +
                                           ", ie. '" + ' '.join(cmd) + "'")
                                    sp = subprocess.Popen(cmd, stdout=Server.devnull, stderr=subprocess.STDOUT)

                                    self.users.append(uid)
                                    self.agents[uid] = sp
                                    self.time_remaining[uid] = self.cycles_per_user

                                    print "Server: ... launched Agent for user " + str(uid)

                                # Even if we already have this user, the file should be removed.
                                files_to_remove.append(fn)

                # Remove flagged files.
                for fn in files_to_remove:
                    path = os.path.join(self.client_dir, fn)
                    cmd = "rm " + path
                    print "Server executing: " + cmd  # DEBUG
                    os.system(cmd)

                # Check for finished users.
                for uid in self.users:
                    if self.agents[uid].poll() is not None:  # None means process hans't terminated yet.
                        print "Server: detected finished user " + str(uid)
                        self.remove_user(uid)
                        print "Server: ... removed user."

                time.sleep(self.spin_time)

                users_for_removal = []
                for uid in self.time_remaining:
                    self.time_remaining[uid] -= 1
                    if self.time_remaining[uid] <= 0:
                        print "Server: user " + str(uid) + " timed out and will be removed"
                        users_for_removal.append(uid)
                for uid in users_for_removal:
                    self.remove_user(uid)
                    print "Server: ... removed user " + str(uid)

        # Clean up upon sigterm.
        except KeyboardInterrupt:
            print "Server: caught interrupt signal; removing all remaining users"
            users_for_removal = self.users[:]
            for uid in users_for_removal:
                self.remove_user(uid)
                print "Server: ... removed user " + str(uid)

    def remove_user(self, uid):
        self.users.remove(uid)
        if self.agents[uid].poll() is None:  # process hasn't terminated yet.
            self.agents[uid].kill()
        del self.agents[uid]
        del self.time_remaining[uid]


# This loads a parser from disk and instantiates a grounder, optionally writing grounding classifiers to file.
# It then instantiates a Server which uses that parser and grounder to create new Agents that communicate
# via a ServerIO instance.
# This is used during Mechanical Turk experiments to facilitate multiple simultaneous users for Agents with the
# same base parser and perception, which are copied for each instance.
def main():

    # Load parameters from command line.
    parser_fn = FLAGS_parser_fn
    kb_static_facts_fn = FLAGS_kb_static_facts_fn
    kb_perception_source_dir = FLAGS_kb_perception_source_dir
    kb_perception_feature_dir = FLAGS_kb_perception_feature_dir
    active_test_set = [int(oidx) for oidx in FLAGS_active_test_set.split(',')]
    active_train_set = [int(oidx) for oidx in FLAGS_active_train_set.split(',')]
    server_spin_time = FLAGS_server_spin_time
    cycles_per_user = FLAGS_cycles_per_user
    client_dir = FLAGS_client_dir
    write_classifiers = FLAGS_write_classifiers

    # Load the parser from file.
    print "main: loading parser from file..."
    with open(parser_fn, 'rb') as f:
        p = pickle.load(f)
    print "main: ... done"

    # Create a new labels.pickle that erases the labels of the active training set for test purposes.
    print "main: creating new labels.pickle that blinds the active training set for this test..."
    with open(os.path.join(kb_perception_source_dir, 'full_annotations.pickle'), 'rb') as f:
        fa = pickle.load(f)
    with open(os.path.join(kb_perception_source_dir, 'labels.pickle'), 'wb') as f:
        labels = []
        for oidx in fa:
            if oidx not in active_train_set:
                for pidx in range(len(fa[oidx])):
                    labels.append((pidx, oidx, fa[oidx][pidx]))
        pickle.dump(labels, f)
    print "main: ... done"

    # Instantiate a grounder.
    print "main: instantiating grounder..."
    g = KBGrounder.KBGrounder(p, kb_static_facts_fn, kb_perception_source_dir, kb_perception_feature_dir,
                              active_test_set)
    if write_classifiers:
        print "main: and writing grounder perception classifiers to file..."
        g.kb.pc.commit_changes()  # save classifiers to disk
    print "main: writing grounder to pickle..."
    grounder_fn = os.path.join(client_dir, 'grounder.pickle')
    with open(grounder_fn, 'wb') as f:
        pickle.dump(g, f)
    print "main: ... done"

    # Start the Server.
    print "main: instantiated server..."
    s = Server(grounder_fn, server_spin_time, cycles_per_user, client_dir)
    print "main: ... done"

    print "main: spinning server..."
    s.spin()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--parser_fn', type=str, required=True,
                        help="a parser pickle to load")
    parser.add_argument('--kb_static_facts_fn', type=str, required=True,
                        help="static facts file for the knowledge base")
    parser.add_argument('--kb_perception_source_dir', type=str, required=True,
                        help="perception source directory for knowledge base")
    parser.add_argument('--kb_perception_feature_dir', type=str, required=True,
                        help="perception feature directory for knowledge base")
    parser.add_argument('--active_test_set', type=str, required=True,
                        help="objects to consider possibilities for grounding; " +
                             "excluded from perception classifier training")
    parser.add_argument('--active_train_set', type=str, required=True,
                        help="objects to consider 'local' and able to be queried by opportunistic active learning")
    parser.add_argument('--server_spin_time', type=int, required=True,
                        help="seconds to spin between disk scans")
    parser.add_argument('--cycles_per_user', type=int, required=False, default=86400,  # ie. one day
                        help="cycles of server spins before terminating a user (time limit)")
    parser.add_argument('--client_dir', type=str, required=True,
                        help="directory where client files should be read")
    parser.add_argument('--write_classifiers', type=int, required=False, default=0,
                        help="whether to write loaded/trained perception classifiers back to disk")
    args = parser.parse_args()
    for k, v in vars(args).items():
        globals()['FLAGS_%s' % k] = v
    main()

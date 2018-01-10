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

    def __init__(self, active_train_set, grounder_fn, spin_time, cycles_per_user,
                 client_dir, log_dir, data_dir,
                 num_dialogs, init_phase):
        self.active_train_set = active_train_set
        self.grounder_fn = grounder_fn
        self.spin_time = spin_time
        self.cycles_per_user = cycles_per_user
        self.client_dir = client_dir
        self.log_dir = log_dir
        self.data_dir = data_dir
        self.num_dialogs = num_dialogs
        self.init_phase = init_phase

        # State and message information.
        self.users = []  # uids
        self.agents = {}  # from uid -> subprocesses running agents
        self.logs = {}  # from uid -> file handles
        self.time_remaining = {}  # from uid -> int

    # Begin to spin forever, checking the disk for relevant communications.
    def spin(self):

        # Spin.
        print "Server: spinning forever..."
        try:
            while True:

                # Walk the filesystem for new inputs from client-side webpage.
                files_to_remove = []  # list of filenames
                user_just_launched = []
                for _, _, files in os.walk(self.client_dir):
                    for fn in files:
                        fnp = fn.split('.')
                        if len(fnp) == 3 and fnp[2] == 'txt':

                            # Check for newly-connected users.
                            if fnp[1] == 'newu':
                                uid = fnp[0]
                                if uid not in self.users:
                                    print "Server: found new user " + uid

                                    # Spawn a process that instantiates an Agent and starts a ServerIO dialog.
                                    cmd = ["python", "main.py",
                                           "--grounder_fn", self.grounder_fn,
                                           "--io_type", "server",
                                           "--uid", uid,
                                           "--client_dir", self.client_dir,
                                           "--data_dir", self.data_dir,
                                           "--spin_time", str(self.spin_time),
                                           "--num_dialogs", str(self.num_dialogs),
                                           "--init_phase", str(self.init_phase)]
                                    if self.active_train_set is not None:
                                        cmd.extend(["--active_train_set", ','.join([str(oidx)
                                                                                   for oidx in self.active_train_set])])
                                    print ("Server: ... executing subprocess " + str(cmd) +
                                           ", ie. '" + ' '.join(cmd) + "'")
                                    f = open(os.path.join(self.log_dir, uid + ".log"), 'w')
                                    sp = subprocess.Popen(cmd, stdout=f, stderr=f)

                                    self.users.append(uid)
                                    self.agents[uid] = sp
                                    self.logs[uid] = f
                                    self.time_remaining[uid] = self.cycles_per_user
                                    user_just_launched.append(uid)

                                    print "Server: ... launched Agent for user " + uid

                                # Even if we already have this user, the file should be removed.
                                files_to_remove.append(fn)

                # Remove flagged files.
                for fn in files_to_remove:
                    path = os.path.join(self.client_dir, fn)
                    cmd = "rm -f " + path
                    print "Server executing: " + cmd  # DEBUG
                    os.system(cmd)

                # Check for finished users.
                for uid in self.users:
                    if uid not in user_just_launched:
                        if self.agents[uid].poll() is not None:  # None means process hans't terminated yet.
                            print "Server: detected finished user " + uid
                            self.remove_user(uid)
                            print "Server: ... removed user."

                time.sleep(self.spin_time)

                users_for_removal = []
                for uid in self.time_remaining:
                    self.time_remaining[uid] -= 1
                    if self.time_remaining[uid] <= 0:
                        print "Server: user " + uid + " timed out and will be removed"
                        users_for_removal.append(uid)
                for uid in users_for_removal:
                    self.remove_user(uid)
                    print "Server: ... removed user " + uid

        # Clean up upon sigterm.
        except KeyboardInterrupt:
            print "Server: caught interrupt signal; removing all remaining users"
            users_for_removal = self.users[:]
            for uid in users_for_removal:
                self.remove_user(uid)
                print "Server: ... removed user " + uid

    def remove_user(self, uid):
        self.users.remove(uid)
        if self.agents[uid].poll() is None:  # process hasn't terminated yet.
            self.agents[uid].terminate()
            print "Server: ... forcibly terminating process for user " + uid
        del self.agents[uid]
        self.logs[uid].close()
        del self.logs[uid]
        del self.time_remaining[uid]


# This loads a parser from disk and instantiates a grounder, optionally writing grounding classifiers to file.
# It then instantiates a Server which uses that parser and grounder to create new Agents that communicate
# via a ServerIO instance.
# This is used during Mechanical Turk experiments to facilitate multiple simultaneous users for Agents with the
# same base parser and perception, which are copied for each instance.
def main():

    # Load parameters from command line.
    parser_fn = FLAGS_parser_fn
    word_embeddings_fn = FLAGS_word_embeddings_fn
    kb_static_facts_fn = FLAGS_kb_static_facts_fn
    kb_perception_source_dir = FLAGS_kb_perception_source_dir
    kb_perception_feature_dir = FLAGS_kb_perception_feature_dir
    active_test_set = [int(oidx) for oidx in FLAGS_active_test_set.split(',')]
    active_train_set = [int(oidx) for oidx in FLAGS_active_train_set.split(',')] if FLAGS_active_train_set is not None else None
    server_spin_time = FLAGS_server_spin_time
    cycles_per_user = FLAGS_cycles_per_user
    client_dir = FLAGS_client_dir
    log_dir = FLAGS_log_dir
    data_dir = FLAGS_data_dir
    write_classifiers = FLAGS_write_classifiers
    load_grounder = FLAGS_load_grounder
    num_dialogs = FLAGS_num_dialogs
    init_phase = FLAGS_init_phase

    # Load the parser from file.
    print "main: loading parser from file..."
    with open(parser_fn, 'rb') as f:
        p = pickle.load(f)
    p.lexicon.wv = p.lexicon.load_word_embeddings(word_embeddings_fn)
    print "main: ... done"

    # Create a new labels.pickle that erases the labels of the active training set for test purposes.
    full_annotation_fn = os.path.join(kb_perception_source_dir, 'full_annotations.pickle')
    if os.path.isfile(full_annotation_fn):
        print "main: creating new labels.pickle that blinds the active training set for this test..."
        with open(full_annotation_fn, 'rb') as f:
            fa = pickle.load(f)
        with open(os.path.join(kb_perception_source_dir, 'labels.pickle'), 'wb') as f:
            labels = []
            for oidx in fa:
                if active_train_set is None or oidx not in active_train_set:
                    for pidx in range(len(fa[oidx])):
                        labels.append((pidx, oidx, fa[oidx][pidx]))
            pickle.dump(labels, f)
        print "main: ... done"

    # Instantiate a grounder.
    grounder_fn = os.path.join(client_dir, 'grounder.pickle')
    if load_grounder != 1:
        print "main: instantiating grounder..."
        g = KBGrounder.KBGrounder(p, kb_static_facts_fn, kb_perception_source_dir, kb_perception_feature_dir,
                                  active_test_set)
        if write_classifiers:
            print "main: and writing grounder perception classifiers to file..."
            g.kb.pc.commit_changes()  # save classifiers to disk
        print "main: writing grounder to pickle..."
        with open(grounder_fn, 'wb') as f:
            pickle.dump(g, f)
        print "main: ... done"

    # Start the Server.
    print "main: instantiated server..."
    s = Server(active_train_set, grounder_fn, server_spin_time, cycles_per_user,
               client_dir, log_dir, data_dir,
               num_dialogs, init_phase)
    print "main: ... done"

    print "main: spinning server..."
    s.spin()


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--parser_fn', type=str, required=True,
                        help="a parser pickle to load")
    parser.add_argument('--word_embeddings_fn', type=str, required=True,
                        help="fresh word embeddings to deal with gensim version differences")
    parser.add_argument('--kb_static_facts_fn', type=str, required=True,
                        help="static facts file for the knowledge base")
    parser.add_argument('--kb_perception_source_dir', type=str, required=True,
                        help="perception source directory for knowledge base")
    parser.add_argument('--kb_perception_feature_dir', type=str, required=True,
                        help="perception feature directory for knowledge base")
    parser.add_argument('--active_test_set', type=str, required=True,
                        help="objects to consider possibilities for grounding; " +
                             "excluded from perception classifier training")
    parser.add_argument('--active_train_set', type=str, required=False, default=None,
                        help="objects to consider 'local' and able to be queried by opportunistic active learning")
    parser.add_argument('--server_spin_time', type=int, required=True,
                        help="seconds to spin between disk scans")
    parser.add_argument('--cycles_per_user', type=int, required=False, default=86400,  # ie. one day
                        help="cycles of server spins before terminating a user (time limit)")
    parser.add_argument('--client_dir', type=str, required=True,
                        help="directory where client files should be read")
    parser.add_argument('--log_dir', type=str, required=True,
                        help="directory where client logfiles should be saved")
    parser.add_argument('--data_dir', type=str, required=True,
                        help="direcotry where we will write out information gathered during dialogs")
    parser.add_argument('--write_classifiers', type=int, required=False, default=0,
                        help="whether to write loaded/trained perception classifiers back to disk")
    parser.add_argument('--load_grounder', type=int, required=False, default=0,
                        help="whether to load the grounder from disk (for testing purposes)")
    parser.add_argument('--num_dialogs', type=int, required=False, default=1,
                        help="number of times to call start_action_dialog per agent")
    parser.add_argument('--init_phase', type=int, required=False, default=0,
                        help="don't actually launch an agent; just ask for the specified number of responses")
    args = parser.parse_args()
    for k, v in vars(args).items():
        globals()['FLAGS_%s' % k] = v
    main()

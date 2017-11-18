#!/usr/bin/env python
__author__ = 'jesse'

import sys
sys.path.append('../tsp/')  # necessary to import CKYParser from above directory

import argparse
import pickle
import Agent
import KBGrounder
import IO
import os


def main():

    # Load parameters from command line.
    parser_fn = FLAGS_parser_fn
    io_type = FLAGS_io_type
    grounder_fn = FLAGS_grounder_fn
    active_train_set = [int(oidx) for oidx in FLAGS_active_train_set.split(',')]
    kb_static_facts_fn = None
    kb_perception_source_dir = None
    kb_perception_feature_dir = None
    active_test_set = None
    if grounder_fn is None:
        kb_static_facts_fn = FLAGS_kb_static_facts_fn
        kb_perception_source_dir = FLAGS_kb_perception_source_dir
        kb_perception_feature_dir = FLAGS_kb_perception_feature_dir
        active_test_set = [int(oidx) for oidx in FLAGS_active_test_set.split(',')]
    write_classifiers = FLAGS_write_classifiers
    uid = FLAGS_uid
    client_dir = FLAGS_client_dir
    spin_time = FLAGS_spin_time
    num_dialogs = FLAGS_num_dialogs
    assert io_type == 'keyboard' or io_type == 'server'
    assert io_type != 'server' or (uid is not None and client_dir is not None)

    if grounder_fn is None:

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
        print "main: ... done"

    else:
        # Load a grounder from file
        print "main: loading grounder from file..."
        with open(grounder_fn, 'rb') as f:
            g = pickle.load(f)
        print "main: ... done"

        # Grab a reference to the parser from the loaded grounder.
        p = g.parser

    # Instantiate an input/output
    print "main: instantiating IO..."
    if io_type == 'keyboard':
        io = IO.KeyboardIO()
    elif io_type == 'server':
        io = IO.SeverIO(uid, client_dir, spin_time=spin_time)
    else:
        io = None  # won't be executed due to asserts
    print "main: ... done"

    # Instantiate an Agent.
    print "main: instantiating Agent..."
    a = Agent.Agent(p, g, io, active_train_set)
    print "main: ... done"

    # Start a dialog.
    for _ in range(num_dialogs):
        print "main: running command dialog..."
        a.start_action_dialog()
        print "main: ... done"

    # Retrain the in-memory parser based on induced training data.
    # print "main: re-training parser on pairs induced from conversation..."
    # a.train_parser_from_induced_pairs(10, 10, 3, verbose=2)
    # print "main: ... done"

    # TODO: for server, need to write out relevant things at dialog's end, such as induced pairs,
    # TODO: new predicates and labels, and new synonymy information from human labels.


if __name__ == '__main__':
    parser = argparse.ArgumentParser()
    parser.add_argument('--parser_fn', type=str, required=False,
                        help="a parser pickle to load")
    parser.add_argument('--io_type', type=str, required=True,
                        help="one of 'keyboard' or 'server'")
    parser.add_argument('--write_classifiers', type=int, required=False, default=0,
                        help="whether to write loaded/trained perception classifiers back to disk")
    parser.add_argument('--grounder_fn', type=str, required=False,
                        help="a grounder pickle to load; if not provided, a new one will be instantiated")
    parser.add_argument('--kb_static_facts_fn', type=str, required=False,
                        help="static facts file for the knowledge base")
    parser.add_argument('--kb_perception_source_dir', type=str, required=False,
                        help="perception source directory for knowledge base")
    parser.add_argument('--kb_perception_feature_dir', type=str, required=False,
                        help="perception feature directory for knowledge base")
    parser.add_argument('--active_test_set', type=str, required=False,
                        help="objects to consider possibilities for grounding; " +
                             "excluded from perception classifier training")
    parser.add_argument('--active_train_set', type=str, required=True,
                        help="objects to consider 'local' and able to be queried by opportunistic active learning")
    parser.add_argument('--uid', type=int, required=False,
                        help="for ServerIO")
    parser.add_argument('--client_dir', type=str, required=False,
                        help="for ServerIO")
    parser.add_argument('--spin_time', type=int, required=False, default=1,
                        help="for ServerIO")
    parser.add_argument('--num_dialogs', type=int, required=False, default=1,
                        help="number of times to call start_action_dialog")
    args = parser.parse_args()
    for k, v in vars(args).items():
        globals()['FLAGS_%s' % k] = v
    main()

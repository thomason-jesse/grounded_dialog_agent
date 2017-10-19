#!/usr/bin/env python
__author__ = 'jesse'

import sys
sys.path.append('../tsp/')  # necessary to import CKYParser from above directory

import argparse
import pickle
import Agent
import KBGrounder
import IO


def main():

    # Load parameters from command line.
    parser_fn = FLAGS_parser_fn
    kb_static_facts_fn = FLAGS_kb_static_facts_fn
    kb_perception_source_dir = FLAGS_kb_perception_source_dir
    kb_perception_feature_dir = FLAGS_kb_perception_feature_dir
    active_test_set = [int(oidx) for oidx in FLAGS_active_test_set.split(',')]
    active_train_set = [int(oidx) for oidx in FLAGS_active_train_set.split(',')]
    io_type = FLAGS_io_type
    write_classifiers = FLAGS_write_classifiers
    assert io_type == 'keyboard' or io_type == 'file' or io_type == 'robot'

    # Load the parser from file.
    print "main: loading parser from file..."
    with open(parser_fn, 'rb') as f:
        p = pickle.load(f)
    print "main: ... done"

    # Instantiate a grounder.
    print "main: instantiating grounder..."
    g = KBGrounder.KBGrounder(p, kb_static_facts_fn, kb_perception_source_dir, kb_perception_feature_dir,
                              active_test_set)
    if write_classifiers:
        print "main: and writing grounder perception classifiers to file..."
        g.kb.pc.commit_changes()  # save classifiers to disk
    print "main: ... done"

    # Instantiate an input/output
    print "main: instantiating specified IO..."
    if io_type == 'keyboard':
        io = IO.KeyboardIO()
    else:
        raise ValueError("io_type '" + io_type + "' is not yet implemented.")
    print "main: ... done"

    # Instantiate an Agent.
    print "main: instantiating Agent..."
    a = Agent.Agent(p, g, io, active_train_set)
    print "main: ... done"

    # Start a dialog.
    print "main: running command dialog..."
    a.start_action_dialog()
    print "main: ... done"

    # Retrain the in-memory parser based on induced training data.
    print "main: re-training parser on pairs induced from conversation..."
    a.train_parser_from_induced_pairs(10, 10, 3, verbose=2)
    print "main: ... done"


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
    parser.add_argument('--io_type', type=str, required=True,
                        help="one of 'keyboard', 'file', or 'robot'")
    parser.add_argument('--write_classifiers', type=int, required=False, default=0,
                        help="whether to write loaded/trained perception classifiers back to disk")
    args = parser.parse_args()
    for k, v in vars(args).items():
        globals()['FLAGS_%s' % k] = v
    main()

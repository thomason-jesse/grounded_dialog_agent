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
    io_type = FLAGS_io_type
    assert io_type == 'keyboard' or io_type == 'file' or io_type == 'robot'

    # Load the parser from file.
    with open(parser_fn, 'rb') as f:
        p = pickle.load(f)

    # Instantiate a grounder.
    g = KBGrounder.KBGrounder(p, kb_static_facts_fn, kb_perception_source_dir, kb_perception_feature_dir)
    # g.kb.pc.commit_changes()  # save classifiers to disk

    # Instantiate an input/output
    if io_type == 'keyboard':
        io = IO.KeyboardIO()
    else:
        raise ValueError("io_type '" + io_type + "' is not yet implemented.")

    # Instantiate an Agent.
    a = Agent.Agent(p, g, io)

    # Start a dialog.
    io.say_to_user("Enter a command: ")
    u = io.get_from_user()
    a.start_action_dialog(u)


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
    parser.add_argument('--io_type', type=str, required=True,
                        help="one of 'keyboard', 'file', or 'robot'")
    args = parser.parse_args()
    for k, v in vars(args).items():
        globals()['FLAGS_%s' % k] = v
    main()
